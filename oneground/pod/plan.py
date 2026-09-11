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
                 data_center_id, candidates, dc_candidates=None,
                 dc_searched=None):
        self.session = session
        self.volume = volume                  # the raw API record, or None
        self.gpu = gpu                        # {id, display_name, ...}
        self.usd_min = usd_min
        self.usd_max = usd_max                # what everything is confirmed at
        self.stock = stock
        self.data_center_id = data_center_id
        self.candidates = candidates          # [(name, min, max, stock)]
        # Volume-less only: the regions that offered the chosen GPU, and how
        # many were searched. Kept so `plan` can show that the region was
        # chosen rather than assumed.
        self.dc_candidates = dc_candidates or []
        self.dc_searched = dc_searched

    @property
    def uses_volume(self):
        return self.volume is not None

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
        spec = {
            "name": "oneground-session-%s" % session_id,
            "imageName": self.session.image,
            "gpuTypeIds": [self.gpu["id"]],
            "gpuCount": 1,
            "cloudType": self.session.cloud_type,
            "computeType": "GPU",
            "dataCenterIds": [self.data_center_id],
            "containerDiskInGb": self.session.disk_gb,
            "env": env,
            "ports": ["22/tcp"],
            "supportPublicIp": True,
        }
        # Both keys are omitted rather than sent as null when there is no
        # volume: `volumeMountPath` without a `networkVolumeId` describes a
        # mount that does not exist, and the mount path is then just a
        # directory on the container disk, which needs no declaring.
        if self.uses_volume:
            spec["networkVolumeId"] = self.volume["id"]
            spec["volumeMountPath"] = self.session.volume_mount_path
        return spec

    # -- rendering ----------------------------------------------------------
    def render(self, session_id="<assigned at up>"):
        s = self.session
        L = []
        A = L.append
        A("session      : %s   (%s)" % (s.name, s.path or "-"))
        A("")
        if self.uses_volume:
            A("  volume     : %s" % self.volume["name"])
            A("               id %s, %s GB" % (self.volume["id"],
                                               self.volume.get("size", "?")))
            A("  datacenter : %s   (derived from the volume, not the spec)"
              % self.data_center_id)
        else:
            A("  volume     : none   (nothing outlives the pod)")
            A("  datacenter : %s   (chosen by GPU availability%s)"
              % (self.data_center_id,
                 "" if self.dc_searched is None
                 else ", %d searched" % self.dc_searched))
            if self.priced:
                A("               cheapest of %d offering %s, at $%.2f/hr"
                  % (len(self.dc_candidates), self.gpu["display_name"],
                     self.usd_max))
        A("  gpu        : %s   [%s]" % (self.gpu["display_name"], self.gpu["id"]))
        A("               stock %s" % self.stock)
        A("  image      : %s" % s.image)
        if self.uses_volume:
            A("  disk       : %d GB container disk, volume at %s"
              % (s.disk_gb, s.volume_mount_path))
        else:
            A("  disk       : %d GB container disk; %s is on it, not a volume"
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
            for n, lo, hi, st in self.candidates) or "-")
          + ("   (in %s)" % self.data_center_id if not self.uses_volume
             else ""))
        if not self.uses_volume and self.dc_candidates:
            A("")
            A("  datacenters offering %s, cheapest first:"
              % self.gpu["display_name"])
            for d, lo, hi, st in self.dc_candidates[:8]:
                A("    %-11s $%s - $%s/hr   stock %s%s"
                  % (d,
                     "?" if lo is None else "%.2f" % lo,
                     "?" if hi is None else "%.2f" % hi,
                     st, "   <- chosen" if d == self.data_center_id else ""))
            if len(self.dc_candidates) > 8:
                A("    ... and %d more" % (len(self.dc_candidates) - 8))
            if self.priced:
                A("  The list price is global, so every region above would be")
                A("  confirmed at the same $%.2f/hr -- the floor is the only"
                  % self.usd_max)
                A("  regional signal, and it only breaks the tie.")
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


def _pick_gpu(prices, session):
    """First GPU in the spec's order that this datacenter actually sells.

    Returns `(chosen_entry_or_None, candidates)`. Split out so the
    volume-derived and volume-less paths cannot drift in what "available"
    means.
    """
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
    return chosen, candidates


def resolve_anywhere(client, session):
    """Session -> Plan for a session with no network volume.

    The rule, in the spec's own words: **the cheapest datacenter offering the
    first available GPU in the list**. The GPU list is a preference order, so
    it is honoured first -- a cheap datacenter for a card the session did not
    ask for is not a better answer, it is a different one. Only once a GPU is
    fixed does price choose between the regions offering it.

    "Cheapest" can only mean the `lowestPrice` floor, because `securePrice` --
    the number this project confirms against -- is reported globally and is the
    same in every region. The ranking is still written worst-case-first so it
    stays correct if that ever changes, and the floor is only ever a tie-break
    between regions, never the number anyone is asked to approve.
    """
    dcs = [d["id"] for d in client.list_datacenters(listed_only=True)]
    if not dcs:
        raise PlanError(
            "the API listed no datacenters, so a region cannot be chosen. A "
            "session with `volume: none` picks its own region; one pinned to "
            "a volume does not need this call.")

    by_dc = client.gpu_prices_across_datacenters(dcs, session.cloud_type)

    # GPU preference order outer, price inner.
    for want in session.gpu:
        offers = []
        for dc in dcs:
            chosen, _cands = _pick_gpu(by_dc.get(dc, {}),
                                       _OneGpu(session, want))
            if chosen is not None:
                offers.append((dc, chosen))
        if not offers:
            continue
        # Worst case first, then the floor, then the id so a tie is stable and
        # a re-run of `plan` cannot silently move the pod to another region.
        offers.sort(key=lambda t: (t[1]["usd_max"], t[1]["usd_min"], t[0]))
        dc, chosen = offers[0]
        considered = [(d, e["usd_min"], e["usd_max"], e["stock"])
                      for d, e in offers]
        _chosen, candidates = _pick_gpu(by_dc.get(dc, {}), session)
        return Plan(session=session, volume=None, gpu=chosen,
                    usd_min=chosen["usd_min"], usd_max=chosen["usd_max"],
                    stock=chosen["stock"], data_center_id=dc,
                    candidates=candidates, dc_candidates=considered,
                    dc_searched=len(dcs))

    tried = ", ".join(session.gpu)
    raise PlanError(
        "none of the requested GPU types is offered on %s in any of the %d "
        "listed datacenters.\n  requested: %s\n"
        "This session sets `volume: none`, so every region was searched and "
        "the answer is not a regional one -- the spec's gpu list has to name "
        "something RunPod is currently selling."
        % (session.cloud_type, len(dcs), tried))


class _OneGpu:
    """`session` narrowed to a single GPU, for reusing `_pick_gpu` per region.

    A shim rather than a second code path: it keeps "is this GPU available on
    this cloud in this datacenter" defined in exactly one place.
    """

    __slots__ = ("gpu", "cloud_type")

    def __init__(self, session, want):
        self.gpu = [want]
        self.cloud_type = session.cloud_type


def resolve(client, session):
    """Session -> Plan, using read-only calls only."""
    if not session.uses_volume:
        return resolve_anywhere(client, session)

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
