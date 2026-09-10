"""Resolve a session spec to a concrete, priced plan. Creates nothing.

`plan` is the dry run, and it is the same code path `up` uses to decide what
to deploy -- so what the developer is asked to confirm is what gets built, not
a summary of it. Every lookup here is a read-only API call.

The order matters, because it is also the order in which things can be wrong:

1.  Volume by name -> its id and, crucially, its **datacenter**. The
    datacenter is never written in the spec; it is derived, so the pod and the
    volume cannot end up in different regions. A network volume can only be
    attached by a pod in its own datacenter, and a mismatch is not an error
    you want to discover after paying for a deploy.
2.  Live prices for that datacenter only. A GPU type that exists globally may
    be unavailable in EU-RO-1, and its global price is then a fiction.
3.  The spec's `gpu` list in order, first one actually offered wins.
4.  Cap arithmetic: max_hours x rate against max_usd.

`Plan.render()` produces the text `plan` prints and `up` shows before the
prompt.
"""

import json


class PlanError(RuntimeError):
    """The session cannot be resolved to something deployable."""


class Plan:
    """A resolved, priced session. Inert -- holding one costs nothing."""

    def __init__(self, session, volume, gpu, usd_min, usd_max, stock,
                 data_center_id, candidates):
        self.session = session
        self.volume = volume                  # the raw API record
        self.gpu = gpu                        # {id, display_name, ...}
        self.usd_min = usd_min
        self.usd_max = usd_max                # what everything is confirmed at
        self.stock = stock
        self.data_center_id = data_center_id
        self.candidates = candidates          # [(name, min, max, stock)]

    @property
    def usd_per_hr(self):
        """The rate this plan is confirmed and budgeted at: the worst case.

        Never the floor. Task 006b confirmed a floor and was billed 2.1x it.
        """
        return self.usd_max

    @property
    def priced(self):
        return self.usd_max is not None

    # -- cap arithmetic -----------------------------------------------------
    @property
    def worst_case_usd(self):
        """max_hours at the TOP of the range, not the bottom."""
        if self.usd_max is None:
            return None
        return self.session.caps.worst_case_usd(self.usd_max)

    @property
    def within_cap(self):
        if self.worst_case_usd is None:
            return False
        return self.worst_case_usd <= self.session.caps.max_usd

    def check_cap(self):
        """Refuse before anything is created. Unpriceable is a refusal too."""
        if not self.priced:
            raise PlanError(
                "price: couldn't-check for %s in %s -- the API returned no "
                "list price for this cloud type, so the worst case is "
                "unknown. `up` refuses rather than falling back to the "
                "datacenter floor, which is what made task 006b confirm "
                "$0.34/hr and pay $0.72/hr."
                % (self.gpu.get("display_name"), self.data_center_id))
        if not self.within_cap:
            raise PlanError(
                "cap exceeded before anything was created: %g hours at up to "
                "$%.2f/hr is $%.2f, over caps.max_usd of $%.2f. Lower "
                "max_hours, raise max_usd, or choose a cheaper GPU."
                % (self.session.caps.max_hours, self.usd_max,
                   self.worst_case_usd, self.session.caps.max_usd))
        return True

    # -- the deploy payload -------------------------------------------------
    def deploy_spec(self, session_id):
        """The exact POST /pods body. Built here, in the read-only module, so
        `plan` can print the same object `up` would send.

        RunPod's pod API has no label primitive -- the POST /pods schema has no
        `labels`/`tags` field (checked against its OpenAPI document). The
        session label is therefore carried twice, in the pod **name** and in an
        **env var**, and `ls` matches on either. The name is what a human sees
        in the RunPod console; the env var survives a rename.
        """
        env = dict(self.session.env)
        env["ONEGROUND_SESSION"] = session_id
        return {
            "name": "oneground-session-%s" % session_id,
            "imageName": self.session.image,
            "gpuTypeIds": [self.gpu["id"]],
            "gpuCount": 1,
            "cloudType": self.session.cloud_type,
            "computeType": "GPU",
            "dataCenterIds": [self.data_center_id],
            "networkVolumeId": self.volume["id"],
            "volumeMountPath": self.session.volume_mount_path,
            "containerDiskInGb": self.session.disk_gb,
            "env": env,
            "ports": ["22/tcp"],
            "supportPublicIp": True,
        }

    # -- rendering ----------------------------------------------------------
    def render(self, session_id="<assigned at up>"):
        s = self.session
        L = []
        A = L.append
        A("session      : %s   (%s)" % (s.name, s.path or "-"))
        A("")
        A("  volume     : %s" % self.volume["name"])
        A("               id %s, %s GB" % (self.volume["id"],
                                           self.volume.get("size", "?")))
        A("  datacenter : %s   (derived from the volume, not the spec)"
          % self.data_center_id)
        A("  gpu        : %s   [%s]" % (self.gpu["display_name"], self.gpu["id"]))
        A("               stock %s" % self.stock)
        A("  image      : %s" % s.image)
        A("  disk       : %d GB container disk, volume at %s"
          % (s.disk_gb, s.volume_mount_path))
        A("  cloud      : %s" % s.cloud_type)
        if s.env:
            A("  env        : %s" % ", ".join("%s=%s" % kv
                                              for kv in sorted(s.env.items())))
        A("  label      : oneground-session=%s  (pod name + ONEGROUND_SESSION)"
          % session_id)
        A("")
        A("  setup      : %s" % (s.setup or "-"))
        A("  run        : %s" % s.run)
        A("               nohup, stdout to %s" % s.remote_log)
        A("  done when  : the run prints %r" % s.done_marker)
        A("")
        if s.outputs:
            A("  outputs")
            for o in s.outputs:
                A("    %s" % o.remote)
                A("      -> %s%s" % (o.local, "  (extract)" if o.extract else ""))
        else:
            A("  outputs    : none declared")
        A("")
        if not self.priced:
            A("  price      : couldn't-check   (no %s list price in %s)"
              % (s.cloud_type, self.data_center_id))
            A("               `up` refuses: the worst case is unknown, and the")
            A("               datacenter floor is not a substitute for it.")
        else:
            A("  price      : $%.2f - $%.2f/hr   (live on-demand range, %s, %s)"
              % (self.usd_min, self.usd_max, s.cloud_type, self.data_center_id))
            A("               confirmed at the TOP of the range, $%.2f/hr"
              % self.usd_max)
        A("  caps       : max_hours %g, max_usd $%.2f, max_concurrent %d"
          % (s.caps.max_hours, s.caps.max_usd, s.caps.max_concurrent))
        if self.priced:
            A("  COST CAP   : %g h x up to $%.2f/hr = up to $%.2f   %s"
              % (s.caps.max_hours, self.usd_max, self.worst_case_usd,
                 "within max_usd" if self.within_cap
                 else "OVER max_usd of $%.2f" % s.caps.max_usd))
        A("  stall      : terminate if the log has not grown for %g min"
          % s.stall_minutes)
        A("")
        # Both ends are needed to print a range. A type absent from this
        # datacenter has no floor (`lo` None) but may still carry a global
        # list price, so `hi is not None` alone is not enough -- and a type
        # stocked here with no list price is the couldn't-check case.
        A("  considered : " + ("  ".join(
            "%s=%s" % (n, ("$%.2f-$%.2f/%s" % (lo, hi, st))
                       if lo is not None and hi is not None
                       else ("couldn't-check" if lo is not None
                             else "unavailable"))
            for n, lo, hi, st in self.candidates) or "-"))
        return "\n".join(L)

    def render_payload(self, session_id="<assigned at up>"):
        return json.dumps(self.deploy_spec(session_id), indent=2, sort_keys=True)


def resolve_volume(client, name):
    """Find a network volume by name; return the record including its DC."""
    volumes = client.list_network_volumes()
    for v in volumes:
        if v.get("name") == name:
            return v
    known = ", ".join(sorted("%s (%s)" % (v.get("name"), v.get("dataCenterId"))
                             for v in volumes)) or "none on this account"
    raise PlanError(
        "no network volume named %r on this account.\nVolumes found: %s\n"
        "The session spec names the volume; the datacenter is derived from "
        "it, so the name has to be the real one." % (name, known))


def resolve(client, session):
    """Session -> Plan, using read-only calls only."""
    volume = resolve_volume(client, session.volume)
    dc = volume.get("dataCenterId")
    if not dc:
        raise PlanError(
            "volume %r reports no dataCenterId, so a pod cannot be placed "
            "with it" % session.volume)

    prices = client.gpu_price_ranges(dc, session.cloud_type)

    candidates = []
    chosen = None
    for want in session.gpu:
        entry = prices.get(want)
        # Also accept the full type id, so a spec may be explicit if it wants.
        if entry is None:
            for e in prices.values():
                if e["id"] == want:
                    entry = e
                    break
        lo = entry["usd_min"] if entry else None
        hi = entry["usd_max"] if entry else None
        stock = entry["stock"] if entry else None
        candidates.append((want, lo, hi, stock))
        # Two conditions, both needed. `usd_min` present means the datacenter
        # stocks the type; `offered_on_cloud` means the cloud this session
        # actually buys sells it. RTX PRO 4500 carries a communityPrice of
        # $0.34 with communityCloud false -- a price for a machine nobody can
        # be given, and the one task 006b confirmed.
        if (chosen is None and entry and lo is not None
                and entry["offered_on_cloud"]):
            chosen = entry

    if chosen is None:
        offered = ", ".join(
            "%s ($%.2f-$%.2f, %s)" % (e["display_name"], e["usd_min"],
                                      e["usd_max"], e["stock"])
            for e in sorted(prices.values(), key=lambda x: x["display_name"])
            if e["usd_min"] is not None and e["usd_max"] is not None
            and e["offered_on_cloud"]) or "nothing"
        raise PlanError(
            "none of the requested GPU types is offered on %s in %s.\n"
            "  requested: %s\n  offered here: %s\n"
            "The datacenter is fixed by the volume, so the spec's gpu list "
            "has to contain something this region actually has."
            % (session.cloud_type, dc, ", ".join(session.gpu), offered))

    return Plan(session=session, volume=volume, gpu=chosen,
                usd_min=chosen["usd_min"], usd_max=chosen["usd_max"],
                stock=chosen["stock"], data_center_id=dc,
                candidates=candidates)
