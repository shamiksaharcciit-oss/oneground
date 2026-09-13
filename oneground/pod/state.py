"""Session records under `.oneground/sessions/<id>.json` (git-ignored).

One small JSON file per session, written the moment a pod exists and updated
as it moves. It is what lets `status`, `fetch`, `watch` and `down` be given an
id instead of a pod id, and what lets `ls` tell an orphan from a pod someone
else on the account is running.

It deliberately holds no secrets: pod id, session name, spec path, start time,
the rate agreed at confirmation, and the caps. The API key is never written
here or anywhere else on disk.

The record is a convenience, not the source of truth. RunPod is the source of
truth for whether a pod exists, which is why `ls` reconciles against the live
account rather than trusting these files -- a record can be stale (the pod was
killed in the web console) and a pod can have no record (this file was deleted,
or the pod was created from another machine).
"""

import datetime
import json
import os
import time

STATE_DIR = os.path.join(".oneground", "sessions")


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def new_session_id(now=None):
    """A short, sortable, human-typable id: 20260909-143355."""
    t = time.gmtime(now if now is not None else time.time())
    return time.strftime("%Y%m%d-%H%M%S", t)


def state_dir(repo_root="."):
    return os.path.join(repo_root, STATE_DIR)


def path_for(session_id, repo_root="."):
    return os.path.join(state_dir(repo_root), session_id + ".json")


def save(record, repo_root="."):
    d = state_dir(repo_root)
    os.makedirs(d, exist_ok=True)
    p = path_for(record["id"], repo_root)
    # newline="\n" for the same reason every other writer in this repo does it:
    # task 002 found Windows text-mode CRLF in artifacts that had to hash the
    # same on two platforms. This file is not hashed, but the habit is cheap.
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump(record, f, indent=2, sort_keys=True)
        f.write("\n")
    return p


def load(session_id, repo_root="."):
    p = path_for(session_id, repo_root)
    if not os.path.exists(p):
        raise FileNotFoundError(
            "no session record at %s. `oneground pod ls` shows what is "
            "actually running on the account." % p)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_all(repo_root="."):
    d = state_dir(repo_root)
    if not os.path.isdir(d):
        return []
    out = []
    for name in sorted(os.listdir(d)):
        if name.endswith(".json"):
            try:
                with open(os.path.join(d, name), encoding="utf-8") as f:
                    out.append(json.load(f))
            except (ValueError, OSError):
                continue
    return out


def live_sessions(repo_root="."):
    """Records not yet marked terminated. Used for the max_concurrent check."""
    return [r for r in load_all(repo_root)
            if r.get("state") not in ("terminated", "failed")]


def record_for(plan, session_id, pod_id, pod=None, candidate=None):
    """Build the record written at `up`.

    `candidate` is what was actually deployed, which is not always what was
    planned: `up` falls through to the next (datacenter, GPU) when a create is
    refused for want of capacity. The record names the machine that exists,
    not the one that was first chosen -- otherwise `status` and `watch` would
    report a card the account never had.
    """
    s = plan.session
    gpu = (candidate or {}).get("gpu") or plan.gpu
    dc = (candidate or {}).get("data_center_id") or plan.data_center_id
    usd_max = (candidate or {}).get("usd_max", plan.usd_max)
    usd_min = (candidate or {}).get("usd_min", plan.usd_min)
    return {
        "id": session_id,
        "session": s.name,
        "spec": s.path,
        "pod_id": pod_id,
        "state": "running",
        "created_at": _now_iso(),
        "started_at_epoch": time.time(),
        "data_center_id": dc,
        "gpu": gpu["display_name"],
        "gpu_type_id": gpu["id"],
        # Set when the pod deployed is not the plan's first choice, so a
        # record that disagrees with the plan above it explains itself.
        "planned_gpu": (plan.gpu["display_name"]
                        if gpu["id"] != plan.gpu["id"] else None),
        # What was confirmed (top of the range) and what the pod actually
        # costs, kept apart. `cost_so_far` uses the true rate once known;
        # before then it uses the confirmed worst case, so the estimate errs
        # high rather than low.
        "usd_per_hr_confirmed": usd_max,
        "usd_per_hr_quoted_min": usd_min,
        "usd_per_hr_true": None,
        "usd_per_hr_at_create": plan.usd_per_hr,   # kept: older records read it
        "caps": {"max_hours": s.caps.max_hours, "max_usd": s.caps.max_usd,
                 "max_concurrent": s.caps.max_concurrent},
        # None for a `volume: none` session. Recorded rather than omitted, so
        # a later reader can tell "no volume" from "record written before
        # volumes existed".
        "volume": plan.volume.get("name") if plan.volume else None,
        "volume_id": plan.volume.get("id") if plan.volume else None,
        "remote_log": s.remote_log,
        "remote_repo": s.remote_repo,
        "done_marker": s.done_marker,
        "stall_minutes": s.stall_minutes,
        "outputs": [{"remote": o.remote, "local": o.local, "extract": o.extract}
                    for o in s.outputs],
        "pod_name": (pod or {}).get("name"),
    }


def mark(session_id, state, repo_root=".", **extra):
    try:
        rec = load(session_id, repo_root)
    except FileNotFoundError:
        return None
    rec["state"] = state
    rec["updated_at"] = _now_iso()
    rec.update(extra)
    save(rec, repo_root)
    return rec


def mark_phase(session_id, name, repo_root=".", when=None):
    """Stamp one setup phase, MERGING with the phases already recorded.

    Task 017f. A plain `mark(..., phase_times={...})` replaces the whole dict,
    so two writers -- `up` stamping RUNNING and `_sync_and_start` stamping the
    sync -- would each erase the other's marks and the record would keep
    whichever wrote last. That is how a field added to answer a question ends
    up answering none of it.
    """
    try:
        rec = load(session_id, repo_root)
    except FileNotFoundError:
        return None
    times = dict(rec.get("phase_times") or {})
    times[name] = float(time.time() if when is None else when)
    return mark(session_id, rec.get("state", "running"), repo_root,
                phase_times=times)


# The phases, in order, and what the gap ENDING at each one measures.
SETUP_PHASES = (
    ("running_at", "RunPod provisioning: create to RUNNING"),
    ("sync_start", "waiting for sshd"),
    ("sync_end", "repo sync: bundle, scp, clone on the pod"),
    ("upload_end", "uploading the session's declared inputs"),
    ("setup_end", "setup script (venv built, or symlinked from the image)"),
    ("launch_start", "starting the run"),
)


def setup_split(record):
    """`[(label, seconds)]` from a record's `phase_times`, or None.

    None rather than zeros when the marks are absent. A session recorded
    before task 017f has no split, and deriving one from `created_at` would be
    precisely the quoted boundary three reports declined to give.
    """
    times = (record or {}).get("phase_times") or {}
    if not times:
        return None
    started = record.get("started_at_epoch")
    out, prev = [], (float(started) if started else None)
    for key, label in SETUP_PHASES:
        t = times.get(key)
        if t is None:
            continue
        if prev is not None:
            out.append((label, round(float(t) - prev, 1)))
        prev = float(t)
    return out or None


def elapsed_hours(record, now=None):
    started = record.get("started_at_epoch")
    if not started:
        return None
    return ((now if now is not None else time.time()) - started) / 3600.0


def cost_so_far(record, now=None):
    """Elapsed hours times the pod's true rate (see `effective_rate`).

    This is an *estimate* and the report says so wherever it is printed. The
    billed figure comes from GET /billing/pods, which lags; this is the number
    available immediately, and it is the one the cap is enforced against.
    """
    h = elapsed_hours(record, now)
    rate = effective_rate(record)
    if h is None or rate is None:
        return None
    return h * rate


def effective_rate(record):
    """The rate to cost at: the pod's true price once known, else the
    confirmed worst case. Never the quoted floor."""
    for key in ("usd_per_hr_true", "usd_per_hr_confirmed",
                "usd_per_hr_at_create"):
        v = record.get(key)
        if v:
            return v
    return None
