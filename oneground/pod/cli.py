"""`oneground pod <subcommand>` -- the command line.

    python -m oneground.pod plan   sessions/arxiv-build.yaml
    python -m oneground.pod up     sessions/arxiv-build.yaml
    python -m oneground.pod status [<id>]
    python -m oneground.pod fetch  <id>
    python -m oneground.pod down   <id>
    python -m oneground.pod watch  <id>
    python -m oneground.pod ls

Only `up` constructs a client that can reach a billable endpoint, and it does
so only after `confirm.ask_to_create()` has returned. Every other subcommand
builds a plain `RunPodClient`, whose guard makes a create call raise rather
than spend -- see `oneground/pod/__init__.py` for why the boundary is drawn
here and why there is no `--yes`.

Exit codes
    0  did what was asked
    1  refused, failed, or the developer answered anything but 'y'
    2  a billable call was attempted without confirmation (a bug; loud)
"""

import argparse
import os
import posixpath
import shlex
import subprocess
import sys
import time

from . import api, confirm, plan as planmod, session as sessionmod, sshx, state


def _repo_root():
    """The repo root, so `local:` paths resolve the same from any cwd."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", ".."))


def _client(args):
    return api.RunPodClient(timeout=args.timeout)


def _redact_dict(d):
    """`api.redact` over every string in a flat record fragment.

    Session records are written to disk and read by a human later. Nothing
    that goes through here should contain the API key -- ssh argv does not --
    but the records are the one place a leak would persist, so they are
    scrubbed on the way in rather than trusted.
    """
    return {k: (api.redact(v) if isinstance(v, str) else v)
            for k, v in (d or {}).items()}


def _fmt_hours(h):
    if h is None:
        return "-"
    return "%dh %02dm" % (int(h), int((h - int(h)) * 60))


# ---------------------------------------------------------------- plan
def cmd_plan(args):
    s = sessionmod.load(args.spec)
    p = planmod.resolve(_client(args), s)
    print()
    print(p.render())
    print()
    if args.payload:
        print("  POST /pods body that `up` would send:")
        print("\n".join("    " + ln
                        for ln in p.render_payload().splitlines()))
        print()
    if not p.within_cap:
        print("  REFUSED: the cost cap is exceeded. `up` would not proceed.")
        return 1
    print("  Nothing was created. This is a dry run; `up` is the only "
          "subcommand that can create a pod.")
    return 0


# ------------------------------------------------- reconciling records
# A pod that is not on the account is not billing, whatever its record says.
# Records go stale routinely: the pod was terminated in the RunPod console, or
# `watch` was killed before it could mark the record, or `down` raced a pod
# that had already gone. Session 20260909-194107 left one behind, and because
# `up` counted it against max_concurrent the next session could not start at
# all -- a stale file blocking work that would have cost nothing to begin.
_RECONCILE_GRACE_SECONDS = 120


def _reconcile_live(client, root, pods=None, now=None, log=print):
    """(live records, records just marked terminated).

    Live means "the pod is on the account", not "the file says running".

    Records younger than the grace window are kept even when their pod is not
    listed yet: GET /pods can lag a create by a few seconds, and treating a
    brand-new pod as absent would let `up` run past max_concurrent. The error
    is deliberately on the expensive side of the boundary -- over-counting
    refuses a session, under-counting creates one.
    """
    now = time.time() if now is None else now
    records = state.live_sessions(root)
    if not records:
        return [], []
    if pods is None:
        try:
            pods = client.list_pods()
        except api.PodApiError as e:
            # Without the account view there is nothing to reconcile against.
            # Trusting the records can only over-count, so it is the safe way
            # to be wrong: say so and leave them alone.
            log("  (could not reach the account to reconcile records: %s)"
                % api.redact(str(e))[:200])
            return records, []
    on_account = {p.get("id") for p in pods if p.get("id")}
    live, reconciled = [], []
    for r in records:
        if r.get("pod_id") in on_account:
            live.append(r)
        elif now - float(r.get("started_at_epoch") or 0) < _RECONCILE_GRACE_SECONDS:
            live.append(r)
        else:
            state.mark(r["id"], "terminated", root,
                       finished_because="absent-from-account")
            reconciled.append(r)
    return live, reconciled


# ---------------------------------------------------------------- up
def cmd_up(args):
    root = _repo_root()
    s = sessionmod.load(args.spec)
    client = _client(args)
    p = planmod.resolve(client, s)

    print()
    print(p.render())
    print()

    # Client-side caps, both checked before the human is asked anything.
    try:
        p.check_cap()
    except planmod.PlanError as e:
        print("REFUSED: %s" % e)
        return 1

    # Before the prompt, before the create, before anything billable.
    if not refuse_if_dirty(root):
        return 1
    if not _inputs_present(s, root):
        return 1

    # Reconciled against the account, not read off the files: a record whose
    # pod no longer exists is not a live session and must not refuse one.
    live, reconciled = _reconcile_live(client, root)
    for r in reconciled:
        print("note: session %s had no pod on the account. Nothing was "
              "billing; its record is now marked terminated." % r["id"])
    if len(live) >= s.caps.max_concurrent:
        print("REFUSED: %d session(s) already live (%s) and caps."
              "max_concurrent is %d. `oneground pod ls` reconciles these "
              "records against the account; `down <id>` releases one."
              % (len(live), ", ".join(r["id"] for r in live),
                 s.caps.max_concurrent))
        return 1

    try:
        token = confirm.ask_to_create(s.name, p.usd_max, s.caps.max_hours,
                                      s.caps.max_usd, usd_min=p.usd_min)
    except confirm.ConfirmationRefused as e:
        print("\nNot created: %s" % e)
        return 1

    session_id = state.new_session_id()

    # The only point in the package where a billable client exists.
    client.allow_create(token.consume())
    try:
        pod, chosen = _create_with_fallthrough(client, p, session_id, token)
    except confirm.ConfirmationRefused as e:
        print("\nNot created: %s" % e)
        return 1
    except api.PodApiError as e:
        print("\nCREATE FAILED: %s" % api.redact(str(e)))
        return 1
    if pod is None:
        return 1
    if chosen is not p.deploy_candidates[0]:
        # The plan printed above is no longer what was built. Say so before
        # anything else is printed against it.
        print("  NOTE: deployed the fallback candidate, not the planned one.")
    pod_id = pod.get("id") or (pod.get("pod") or {}).get("id")
    if not pod_id:
        # The one post-create failure that cannot be cleaned up automatically:
        # there is no id to terminate. It says so at full volume rather than
        # pretending this is an ordinary error.
        print("CREATE RETURNED NO POD ID: %s" % api.redact(str(pod))[:400])
        print("A pod may exist and may be billing, and this process cannot "
              "terminate what it cannot name.")
        print("  oneground pod ls           # reconcile against the account")
        print("  https://console.runpod.io  # and check by eye as well")
        return 1

    # Everything past this line is guarded. The pod exists and the meter is
    # running, so no way out of here -- exception, interrupt or return -- may
    # leave it alive.
    #
    # The guarantee is deliberately a property of this one `try` around one
    # call, rather than a discipline each future branch has to remember.
    # Session 20260909-202938 leaked a pod through the only post-create path
    # that had not been thought about yet, which is the shape this class of
    # bug will always have.
    try:
        return _run_session(client, args, s, p, root, session_id, pod_id,
                            pod, chosen)
    except sshx.LaunchFailed as e:
        # The remote launch returned non-zero or refused to confirm. Nothing
        # ever started, and the pod is billing for it.
        print("\nLAUNCH FAILED -- the run never started.")
        print(api.redact(str(e)))
        state.mark(session_id, "running", root,
                   launch_error=api.redact(str(e)), launch=e.as_dict())
        _terminate(client, session_id, pod_id, root, "launch-failed")
        return 1
    except Exception as e:
        print("\nFAILED after the pod was created: %s" % api.redact(str(e)))
        extra = {"last_error": api.redact(str(e))}
        # Any SSH failure, not only the readiness probe, leaves the command
        # behind. The timeout path used to record neither the command nor the
        # streams, so session 20260911-200558's record could not say what had
        # hung -- only that something had.
        if isinstance(e, sshx.SshError):
            extra["last_ssh"] = _redact_dict(e.as_dict())
        state.mark(session_id, "running", root, **extra)
        _terminate(client, session_id, pod_id, root, "failed-after-create")
        return 1
    except BaseException:
        # Ctrl-C, or anything else that is not an ordinary error. The pod does
        # not care that a human changed their mind; it bills either way. So it
        # is terminated first and the interrupt re-raised afterwards.
        print("\nINTERRUPTED after the pod was created.")
        _terminate(client, session_id, pod_id, root, "interrupted")
        raise


def _create_with_fallthrough(client, p, session_id, token, log=print):
    """Create the pod, falling through the plan's candidates on no-capacity.

    Returns `(pod, candidate)`; `(None, None)` when every candidate was
    refused.

    Why this does not re-prompt. `ask_to_create` shows a **rate** and a total
    and names no GPU, so what the developer authorised is a ceiling. A
    candidate at or under the rate already confirmed is inside that
    authorisation; one above it is not, and is asked about separately. Session
    20260911 failed three creates in a row -- EU-CZ-1 RTX 4090 twice, EU-RO-1
    RTX PRO 4500 once, all "Low" stock -- and each one ended the session and
    made a human retype 'y' for a machine they had already agreed to pay for.

    Why only this one error. `api.is_no_capacity` matches the one refusal that
    states plainly that nothing was allocated. Every other create failure may
    have made a pod whose id this process never saw, and retrying it could put
    two pods behind one confirmation. Those propagate untouched.
    """
    candidates = p.deploy_candidates
    within = p.candidates_within(token.usd_per_hr)
    tried = []

    for i, cand in enumerate(candidates, 1):
        name = cand["gpu"]["display_name"]
        dc = cand["data_center_id"]
        rate = cand["usd_max"]

        if cand not in within:
            # Above the ceiling the developer agreed to. Nothing here re-asks
            # on its own: `up` stops and says what it would have needed.
            log("  attempt %d/%d skipped: %s in %s is $%.2f/hr, above the "
                "$%.2f/hr already confirmed. A dearer card needs a new 'y'."
                % (i, len(candidates), name, dc,
                   rate if rate is not None else float("nan"),
                   token.usd_per_hr))
            continue

        log("  attempt %d/%d: %s in %s at up to $%.2f/hr ..."
            % (i, len(candidates), name, dc, rate))
        try:
            pod = client.create_pod(p.deploy_spec(session_id, cand))
        except api.PodApiError as e:
            if not api.is_no_capacity(e):
                raise
            tried.append("%s/%s" % (dc, name))
            log("    no instances available. Falling through -- nothing was "
                "created, and the next candidate is no dearer.")
            continue
        log("  created on %s in %s at up to $%.2f/hr." % (name, dc, rate))
        return pod, cand

    over = [c for c in candidates if c not in within]
    log("\nNO CAPACITY: every candidate at or under the confirmed "
        "$%.2f/hr was refused (%s)." % (token.usd_per_hr,
                                        ", ".join(tried) or "none tried"))
    if over:
        log("  %d dearer candidate(s) were not tried: %s."
            % (len(over), ", ".join(
                "%s/%s $%.2f/hr" % (c["data_center_id"],
                                    c["gpu"]["display_name"], c["usd_max"])
                for c in over[:4])))
        log("  Re-run `up` to confirm one of those, or wait for stock.")
    log("  Nothing was created and nothing is billing.")
    return None, None


def _wait_ssh_ready(ssh, timeout, log=print):
    """Seam for the readiness probe, so it can be stubbed like `_wait_running`.

    A module-level function rather than a bare `ssh.wait_ready(...)` call
    because this is the one post-create step that does real network work
    before anything under test has happened: a harness driving `up` to a later
    step would otherwise spend the full readiness window trying to reach a pod
    that does not exist.
    """
    return ssh.wait_ready(timeout=timeout, log=log)


def _run_session(client, args, s, p, root, session_id, pod_id, pod,
                 candidate=None):
    """The whole of `up` after the create. Raises; never cleans up itself.

    Cleanup belongs to the single guard in `cmd_up`. This function's job is to
    fail honestly and let that guard stop the meter.
    """
    rec = state.record_for(p, session_id, pod_id, pod, candidate)
    rec_path = state.save(rec, root)
    print("  pod id     : %s" % pod_id)
    print("  session    : %s" % session_id)
    print("  record     : %s" % rec_path)

    # The price actually charged, checked against the price confirmed. Task
    # 006b confirmed $0.34/hr and was handed a $0.72/hr machine; nothing
    # noticed, and the cap survived only because it was bounded in hours.
    # Checked against the rate actually confirmed, which is the ceiling the
    # developer agreed to -- not the fallback's own quote. A cheaper card
    # deployed under that ceiling is inside the authorisation; a pod billing
    # above it is not, whichever candidate it came from.
    true_rate = _check_true_price(client, root, session_id, pod_id, pod,
                                  p.usd_max, args.price_tolerance)
    if true_rate is None:
        return 1              # _check_true_price has already terminated
    print("  IMPORTANT  : this pod is now billing at $%.2f/hr. "
          "`oneground pod down %s` stops it." % (true_rate, session_id))

    pod = _wait_running(client, pod_id, args.boot_timeout)
    # Task 017f. RUNNING is where the setup-time question starts: everything
    # before it is RunPod provisioning a machine, everything after it is ours.
    # Three sessions could not answer "did the baked image help" because this
    # instant was never written down.
    state.mark_phase(session_id, "running_at", root)
    ssh = sshx.PodSsh.from_pod(pod, key_path=args.ssh_key)

    # RUNNING is the container's state, not sshd's. Session 20260911-200558
    # went straight from RUNNING to an scp that hung for 60 s and died with
    # nothing to show but the known-hosts line. Probe first, with a command
    # that is allowed to fail, and record the attempt either way.
    print("waiting for sshd on %s:%d ..." % (ssh.host, ssh.port))
    try:
        ready = _wait_ssh_ready(ssh, args.ssh_ready_timeout)
    except sshx.SshNotReady as e:
        print("\nSSH NEVER CAME UP: %s" % api.redact(str(e)))
        state.mark(session_id, "running", root, ssh_host=ssh.host,
                   ssh_port=ssh.port, ssh_ready=False,
                   ssh_error=_redact_dict(e.as_dict()))
        _terminate(client, session_id, pod_id, root, "ssh-never-ready")
        return 1
    state.mark(session_id, "running", root, ssh_host=ssh.host,
               ssh_port=ssh.port, ssh_ready=ready)

    launch = _sync_and_start(ssh, s, root, session_id, pod_id)
    # The launch's own exit code and streams go in the session record, so a
    # run that did not start leaves evidence rather than a bare pid. Task
    # 011's session 20260909-184937 reported "pid 361" and recorded nothing
    # else; there was no way afterwards to tell whether the command had
    # failed, gone to the wrong path, or never run.
    state.mark(session_id, "running", root, ssh_host=ssh.host,
               ssh_port=ssh.port, launch=launch)
    if not _await_first_log(ssh, s, args.log_timeout):
        print("\nNO RUN: %s never appeared in %d s. The pod has nothing to "
              "wait for." % (s.remote_log, args.log_timeout))
        _terminate(client, session_id, pod_id, root, "no-run")
        return 1
    print("\nrun started. `oneground pod watch %s` will fetch and terminate "
          "at DONE, the cap, or a stall." % session_id)
    return 0


def uncommitted_paths(root):
    """Every path `git bundle --all` would leave behind.

    Modified tracked files *and* untracked ones. Files git ignores are
    excluded, because `git status --porcelain` excludes them and they are
    deliberately not part of the repo -- a scratch output should not block a
    session.
    """
    p = subprocess.run(["git", "-C", root, "status", "--porcelain"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return [ln for ln in (p.stdout or "").splitlines() if ln.strip()]


def refuse_if_dirty(root, log=print):
    """True if the tree is clean. Prints the refusal and returns False if not.

    Called **before** the confirmation prompt and therefore before any
    billable call: a session that cannot carry the developer's code is not a
    session worth being asked to pay for.
    """
    dirty = uncommitted_paths(root)
    if not dirty:
        return True
    log("")
    log("REFUSED: the working tree has %d uncommitted path(s)." % len(dirty))
    for ln in dirty[:20]:
        log("    %s" % ln)
    if len(dirty) > 20:
        log("    ... and %d more" % (len(dirty) - 20))
    log("")
    log("  A bundle carries commits, not the working tree, so none of these")
    log("  would reach the pod -- including new files, which is how task 011's")
    log("  first session cloned a repo with no runner script and failed after")
    log("  the pod was already billing.")
    log("")
    log("  Commit them, then run `up` again. There is no flag to skip this:")
    log("  a pod that cannot run your code is not worth paying for, and a")
    log("  warning printed after the pod exists is on the wrong side of the")
    log("  money boundary.")
    log("")
    return False


def pod_true_rate(pod):
    """The rate a pod is actually charged at, from its own record."""
    for key in ("costPerHr", "adjustedCostPerHr"):
        v = (pod or {}).get(key)
        if v:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None


def _check_true_price(client, root, session_id, pod_id, created,
                      confirmed_max, tolerance):
    """Compare what the pod costs against what the developer agreed to.

    Returns the true rate, or None after terminating the pod. A pod costing
    materially more than was confirmed is not a pod anyone authorised, so it
    is destroyed immediately rather than reported and left running.
    """
    rate = pod_true_rate(created)
    if rate is None:
        # The create response did not carry a price; ask the pod itself.
        try:
            rate = pod_true_rate(client.get_pod(pod_id))
        except api.PodApiError:
            rate = None

    if rate is None:
        print("  price      : couldn't-check -- the pod reports no costPerHr.")
        print("  TERMINATING: an unpriced pod cannot be held against a cap.")
        _terminate(client, session_id, pod_id, root, "price-unknown")
        return None

    state.mark(session_id, "running", root, usd_per_hr_true=rate)
    limit = confirmed_max * (1.0 + tolerance)
    print("  confirmed  : up to $%.2f/hr" % confirmed_max)
    print("  actual     : $%.2f/hr" % rate)
    if rate > limit:
        over = (rate / confirmed_max - 1.0) * 100.0
        print("  PRICE OVER CONFIRMED by %.1f%% (tolerance %.0f%%)."
              % (over, tolerance * 100))
        print("  TERMINATING: this pod costs more than was agreed to.")
        _terminate(client, session_id, pod_id, root, "price-exceeded")
        return None
    return rate


def _terminate(client, session_id, pod_id, root, reason):
    """Terminate and record why. Never leaves the caller guessing."""
    print("  terminating pod %s (%s) ..." % (pod_id, reason))
    try:
        client.terminate_pod(pod_id)
        state.mark(session_id, "terminated", root, finished_because=reason)
        print("  terminated.")
        return True
    except api.PodApiError as e:
        print("  TERMINATE FAILED: %s" % api.redact(str(e))[:300])
        print("  THE POD MAY STILL BE BILLING. Terminate it in the RunPod "
              "console, or `oneground pod down %s`." % pod_id)
        return False


def _await_first_log(ssh, s, timeout):
    """Wait for the run's log to appear. False means nothing ever started.

    Task 006b's first pod reached this point with a launch that had silently
    failed, and then billed for ten minutes with no run and nothing watching.
    The log appearing is the cheapest available proof that something ran.
    """
    print("waiting for the run's log to appear (up to %d s) ..." % timeout)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if ssh.log_size(s.remote_log) is not None:
                print("  log is there; the run is producing output.")
                return True
        except (sshx.SshError, OSError):
            pass
        time.sleep(5)
    return False


def _wait_running(client, pod_id, timeout):
    print("waiting for RUNNING (up to %ds) ..." % timeout)
    deadline = time.time() + timeout
    while time.time() < deadline:
        pod = client.get_pod(pod_id)
        status = pod.get("desiredStatus")
        mappings = pod.get("portMappings") or {}
        if status == "RUNNING" and pod.get("publicIp") and (
                mappings.get("22") or mappings.get(22)):
            print("  RUNNING, ssh %s:%s" % (pod.get("publicIp"),
                                            mappings.get("22")
                                            or mappings.get(22)))
            return pod
        time.sleep(5)
    raise sshx.SshError(
        "pod %s did not reach RUNNING with an SSH mapping within %ds"
        % (pod_id, timeout))


def _input_bytes(local):
    if os.path.isdir(local):
        n = 0
        for dirpath, _d, filenames in os.walk(local):
            for name in filenames:
                n += os.path.getsize(os.path.join(dirpath, name))
        return n
    return os.path.getsize(local)


def _inputs_present(s, root, log=print):
    """Every required input exists, and they fit the cap. Checked before the
    create, because both answers cost money to learn on a pod.

    Session 20260909-195824 spent four minutes of pod time discovering a
    missing file; session 20260909-202938 spent a pod discovering that the
    upload path did not work. Neither question needs a pod to answer.
    """
    missing = [i.local for i in s.inputs
               if not i.optional and not os.path.exists(i.local_path(root))]
    if missing:
        log("REFUSED: the session declares input(s) that do not exist "
            "locally, so the run would fail on the pod after it started "
            "billing:")
        for m in missing:
            log("    %s" % m)
        log("  For a verify session these are the characterize workdir's "
            "files. Run `oneground characterize <requirements>` first.")
        return False

    present = [i for i in s.inputs if os.path.exists(i.local_path(root))]
    total = sum(_input_bytes(i.local_path(root)) for i in present)
    cap = int(s.input_size_cap_mb * 1024 * 1024)
    if total > cap:
        log("REFUSED: the session declares %.1f MB of inputs and its cap is "
            "%g MB." % (total / 1048576.0, s.input_size_cap_mb))
        for i in sorted(present,
                        key=lambda i: -_input_bytes(i.local_path(root)))[:10]:
            log("    %-52s %8.2f MB"
                % (i.local, _input_bytes(i.local_path(root)) / 1048576.0))
        log("")
        log("  scp is the wrong way to move that much data onto a pod, and a")
        log("  transfer that fails does so with the meter already running.")
        log("  Either put the large files on the network volume and point the")
        log("  session at them there, or raise the cap deliberately:")
        log("")
        log("      input_size_cap_mb: %d" % max(1, int(total / 1048576.0) + 1))
        log("")
        log("  in the session spec. There is no command-line flag for this.")
        return False
    return True


def _upload_inputs(ssh, s, root):
    """Put the declared inputs on the pod. Returns a list of (local, remote).

    One archive, one scp, one extract -- three connections however many files
    the session declares. The first version opened two per file (an `ssh
    mkdir -p` and an `scp`), and session 20260909-202938 died on one of the
    `mkdir`s at its 120 s limit while moving a grand total of 258 KB. Twelve
    handshakes to move a quarter of a megabyte was the defect; the timeout was
    only where it surfaced.

    Runs after the clone and before setup, so the run finds the files wherever
    the spec put them -- typically inside the cloned repo, at the same
    relative path the local workdir has.
    """
    if not s.inputs:
        return []
    pairs, placed = [], []
    for inp in s.inputs:
        local = inp.local_path(root)
        if not os.path.exists(local):
            # Only optional inputs can reach here: `up` refused the rest.
            print("  %s: not present locally, skipped (optional)" % inp.local)
            continue
        pairs.append((local, inp.remote))
        placed.append((inp.local, inp.remote))
    if not pairs:
        return []

    print("packing %d declared input(s) the git bundle cannot carry ..."
          % len(pairs))

    def report(local, remote, nbytes):
        print("    %-52s %10s bytes" % (os.path.relpath(local, root)
                                        .replace("\\", "/"),
                                        "{:,}".format(nbytes)))

    archive, total, count = sshx.tar_to_absolute_paths(pairs, on_file=report)
    try:
        packed = os.path.getsize(archive)
        timeout = sshx.transfer_timeout(packed)
        print("  %d file(s), %s bytes -> %s bytes packed; "
              "allowing %ds for the transfer"
              % (count, "{:,}".format(total), "{:,}".format(packed), timeout))
        remote_tgz = "/workspace/oneground-inputs.tgz"
        ssh.put(archive, remote_tgz, timeout=timeout)
        # Rooted at `/` because every member name is its own absolute remote
        # path minus the leading slash. Nothing outside those paths is in the
        # archive -- this function built it a dozen lines ago.
        q = shlex.quote(remote_tgz)
        ssh.run("tar -xzf %s -C / --no-same-owner --no-same-permissions "
                "&& rm -f %s" % (q, q), timeout=timeout)
    finally:
        os.remove(archive)
    print("  unpacked on the pod.")
    return placed


def _sync_and_start(ssh, s, root, session_id, pod_id=None):
    """Bundle the repo, clone it on the pod, run setup, launch the command.

    Task 017f instruments the phases. Three sessions reported the setup-time
    split as couldn't-check -- not because it is hard to measure, but because
    nothing wrote down when each phase began and ended, so the only honest
    answer was the total from `created_at` to the run's first log line. The
    baked image was supposed to be judged on exactly this number.
    """
    def phase(name):
        if session_id:
            state.mark_phase(session_id, name, root)

    phase("sync_start")
    print("syncing repo (git bundle over scp) ...")
    bundle, dirty = sshx.bundle_repo(root)
    if dirty:
        # Should be unreachable: `up` refuses a dirty tree before creating
        # anything. Kept because this function is also reachable from a
        # future caller that has not learned the lesson yet.
        print("  WARNING: %d uncommitted path(s) will NOT reach the pod, "
              "including new files --" % len(dirty))
        for ln in dirty[:10]:
            print("    %s" % ln)
        print("  a bundle carries commits, not the working tree.")
    # With a network volume the mount path already exists. With `volume: none`
    # it is an ordinary directory on the container disk and nothing has made it
    # yet, so the first scp into it would fail. Idempotent, and cheap enough
    # not to be worth branching on.
    ssh.run("mkdir -p %s" % shlex.quote(s.volume_mount_path), timeout=60)
    remote_bundle = "/workspace/oneground.bundle"
    ssh.put(bundle, remote_bundle)

    # The pod must run the commit that was bundled, and must say so. Session
    # 20260911-001111 failed here on a hard-coded `git checkout master` after
    # the branch was renamed; worse, while that line worked it would have
    # checked out the DEFAULT branch, so a task branch's session measured code
    # the task had not written. See sshx.clone_command.
    commit, branch = sshx.head_commit(root)
    print("  bundling %s at %s" % (branch or "(detached)", (commit or "?")[:12]))
    try:
        p = ssh.run(sshx.clone_command(remote_bundle, s.remote_repo,
                                       commit=commit or None), timeout=600)
    except sshx.SshError as e:
        # Everything the clone said, kept where a later reader can find it.
        # The exception message carries only the tail.
        if session_id:
            state.mark(session_id, "clone_failed", repo_root=root,
                       clone_stdout=getattr(e, "stdout", ""),
                       clone_stderr=getattr(e, "stderr", ""),
                       clone_tail=sshx.tail_lines(
                           getattr(e, "stderr", "")
                           or getattr(e, "stdout", ""), 20),
                       clone_returncode=getattr(e, "returncode", None),
                       repo_commit=commit, repo_branch=branch)
        raise
    # `run` returns a CompletedProcess in the real client; a test double may
    # return nothing, and the confirmation line is not worth a crash.
    for ln in sshx.tail_lines(getattr(p, "stdout", "") or "", 3).splitlines():
        print("    %s" % ln)
    if session_id:
        state.mark(session_id, "cloned", repo_root=root,
                   repo_commit=commit, repo_branch=branch)
    print("  cloned to %s" % s.remote_repo)
    phase("sync_end")

    _upload_inputs(ssh, s, root)
    phase("upload_end")

    setup_script = _setup_script(s)
    if setup_script:
        # Not "venv on local disk" any more: with the baked image this step
        # symlinks a venv that is already there, and the script itself decides
        # which. Saying the wrong one here was actively misleading in session
        # 20260912-165508, where it read as evidence that the pre-image path
        # had run -- it had not; the script died in its own env exports,
        # before it ever looked for the marker.
        print("running setup (the script reports which venv it used) ...")
        ssh.run(setup_script, timeout=3600)
        print("  setup complete")
    phase("setup_end")

    phase("launch_start")
    print("starting run under nohup ...")
    # The spec's env, plus the two things only `up` knows: which session this
    # is and which pod it landed on. `environment_id` is derived from the pod
    # id, and a run that cannot name its own machine produces latency numbers
    # no verdict is allowed to use.
    env = dict(s.env)
    env["ONEGROUND_SESSION"] = session_id
    if pod_id:
        env["RUNPOD_POD_ID"] = pod_id
    launch = ssh.start_run(s.remote_repo, s.run, s.remote_log, env=env)
    print("  launched pid %s, stdout -> %s" % (launch["pid"], s.remote_log))
    if launch.get("stderr"):
        print("  launch stderr: %s" % launch["stderr"][:400])
    return launch


def _setup_script(s):
    """The venv setup: symlinked from the baked image, or built on local disk.

    Without the baked image the venv is built at /root/.venv -- container disk
    -- and symlinked into the repo. Populating it on the network volume took
    ~30 minutes; local disk is minutes. `--copies` matters: a symlinked venv on
    a network mount is where much of that time went.

    The env is exported through `sshx.export_lines`, the same function the
    launch uses. It used to have its own unquoted copy, which is what killed
    session 20260912-165508 at line 5 of this script.
    """
    env_lines = sshx.export_lines(s.env)
    return """set -euo pipefail
{env}
cd {repo}
if [ -f /opt/oneground-image/BAKED ]; then
    # Task 017: the pre-baked image already carries the pinned venv. Symlink
    # it rather than building one -- this is the step that cost ~5 minutes of
    # billed time per session, and the whole point of baking the image.
    echo "baked image detected; using the pre-built venv"
    cat /opt/oneground-image/BAKED
    ln -sfn /opt/oneground-venv {repo}/.venv
else
    python3.12 -m venv --copies /root/.venv
    ln -sfn /root/.venv {repo}/.venv
    . /root/.venv/bin/activate
    python -m pip install --upgrade pip
    pip install -r requirements.txt
fi
. {repo}/.venv/bin/activate
python -c "import numpy, torch; print('numpy', numpy.__version__, 'torch', torch.__version__, torch.version.cuda, torch.cuda.is_available())"
""".format(env=env_lines, repo=s.remote_repo)


# ---------------------------------------------------------------- status
def cmd_status(args):
    root = _repo_root()
    client = _client(args)
    if args.id:
        records = [state.load(args.id, root)]
    else:
        records = state.load_all(root)
        if not records:
            print("no session records under .oneground/sessions/. "
                  "`oneground pod ls` shows pods on the account.")
            return 0

    for rec in records:
        print()
        print("session %s   (%s)" % (rec["id"], rec.get("session", "?")))
        print("  pod        : %s" % rec.get("pod_id"))
        try:
            pod = client.get_pod(rec["pod_id"])
        except api.PodApiError as e:
            print("  state      : gone from the account (%s)"
                  % api.redact(str(e))[:120])
            print("  record says: %s" % rec.get("state"))
            continue

        h = state.elapsed_hours(rec)
        est = state.cost_so_far(rec)
        caps = rec.get("caps", {})
        print("  state      : %s" % pod.get("desiredStatus"))
        print("  gpu / dc   : %s / %s" % (rec.get("gpu"),
                                          rec.get("data_center_id")))
        print("  elapsed    : %s of %g h cap" % (_fmt_hours(h),
                                                 caps.get("max_hours", 0)))
        rate = pod.get("costPerHr") or rec.get("usd_per_hr_at_create")
        print("  rate       : $%.2f/hr" % rate if rate else "  rate       : -")
        if est is not None:
            print("  cost so far: ~$%.2f  (estimate: elapsed x rate, not the "
                  "billed figure)" % est)
        billed = _billed(client, rec["pod_id"])
        if billed is not None:
            print("  billed     : $%.4f  (GET /billing/pods; lags)" % billed)
        # Task 017f: the setup split, so "did the baked image help" has an
        # answer that is not a single total with a guess inside it.
        split = state.setup_split(rec)
        if split:
            print("  setup split:")
            for label, secs in split:
                print("    %6.1f s  %s" % (secs, label))
            print("    %6.1f s  total, create to run start"
                  % sum(s2 for _, s2 in split))

        if args.no_logs:
            continue
        try:
            ssh = sshx.PodSsh.from_pod(pod, key_path=args.ssh_key)
            print("  last %d log lines from %s:" % (args.lines,
                                                    rec.get("remote_log")))
            for ln in ssh.tail_log(rec.get("remote_log"),
                                   args.lines).splitlines():
                print("    %s" % ln)
        except (sshx.SshError, OSError) as e:
            print("  logs       : couldn't-check (%s)"
                  % api.redact(str(e))[:160])
    return 0


def _billed(client, pod_id):
    try:
        rows = client.pod_billing(pod_id)
    except api.PodApiError:
        return None
    if not isinstance(rows, list):
        rows = (rows or {}).get("data", [])
    total = 0.0
    for r in rows or []:
        try:
            total += float(r.get("amount") or 0)
        except (TypeError, ValueError):
            pass
    return total if rows else None


# ---------------------------------------------------------------- fetch
def cmd_fetch(args):
    root = _repo_root()
    rec = state.load(args.id, root)
    client = _client(args)
    pod = client.get_pod(rec["pod_id"])
    ssh = sshx.PodSsh.from_pod(pod, key_path=args.ssh_key)
    return _fetch_outputs(ssh, rec, root)


def provenance_warning(tarball, root):
    """Name the files a tarball will NOT replace, before it is extracted.

    Task 006b extracted a build over `fixtures/arxiv-smoke/`. The tarball
    carried 8 of the 11 manifest entries, so `vectors.npy` and `queries.npy`
    stayed behind as the laptop's copies while `MANIFEST.sha256` became the
    pod's -- and the verifier reported 2 contradicted, which looked like a
    corrupt build rather than what it was: two provenances in one directory.

    This does not block. Mixed provenance is sometimes exactly what is wanted;
    being silent about it is not.
    """
    import tarfile

    lines = []
    try:
        with tarfile.open(tarball, "r:gz") as tf:
            members = [m.name for m in tf.getmembers() if m.isfile()]
    except (tarfile.TarError, OSError):
        return lines

    manifests = [m for m in members if os.path.basename(m) == "MANIFEST.sha256"]
    if not manifests:
        return lines

    for man in manifests:
        rel_dir = os.path.dirname(man)
        target = os.path.normpath(os.path.join(root, rel_dir))
        if not os.path.isdir(target):
            continue
        carried = {os.path.basename(m) for m in members
                   if os.path.dirname(m) == rel_dir}
        present = {n for n in os.listdir(target)
                   if os.path.isfile(os.path.join(target, n))}
        stale = sorted(present - carried)
        if not stale:
            continue
        lines.append("  PROVENANCE: %s already holds %d file(s) this tarball "
                     "does not carry." % (rel_dir or ".", len(stale)))
        for n in stale:
            lines.append("    %s   <- local, not from this build" % n)
        lines.append("    They will be checked against the incoming MANIFEST "
                     "and may report as contradicted.")
    return lines


def _fetch_outputs(ssh, rec, root):
    outputs = rec.get("outputs") or []
    if not outputs:
        print("session %s declares no outputs" % rec["id"])
        return 0
    failures = 0
    for o in outputs:
        remote, local = o["remote"], o["local"]
        dest_dir = os.path.normpath(os.path.join(root, local))
        name = os.path.basename(remote)
        dest = dest_dir if not os.path.splitext(dest_dir)[1] else dest_dir
        if os.path.isdir(dest) or local.endswith(("/", "\\")) or local in (".", "./"):
            dest = os.path.join(dest_dir, name)
        print("fetching %s" % remote)
        if not ssh.exists(remote):
            print("  couldn't-check: not present on the pod")
            failures += 1
            continue
        try:
            ssh.get(remote, dest, timeout=3600)
        except sshx.SshError as e:
            print("  FAILED: %s" % api.redact(str(e))[:300])
            failures += 1
            continue
        size = os.path.getsize(dest)
        print("  -> %s  (%d bytes)" % (dest, size))
        if o.get("extract"):
            for line in provenance_warning(dest, root):
                print(line)
            # Into the directory the tarball was fetched into -- which is the
            # output's own `local`, resolved against the repo root. Extracting
            # into `root` regardless is how session 20260909-220900's result
            # ended up in a stray `<repo>/arxiv-smoke/` while `report` went on
            # reading the stale file in `runs/arxiv-smoke/`. For an output
            # that says `local: ./` this is still the repo root, so the
            # arxiv-build session is unaffected.
            extract_dir = os.path.dirname(os.path.abspath(dest))
            os.makedirs(extract_dir, exist_ok=True)
            print("  extracting into %s" % extract_dir)
            p = subprocess.run(["tar", "-xzf", dest, "-C", extract_dir],
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            if p.returncode != 0:
                print("  extract FAILED: %s" % (p.stderr or "")[:300])
                failures += 1
            else:
                print("  extracted")
    return 1 if failures else 0


# ---------------------------------------------------------------- down
def cmd_down(args):
    root = _repo_root()
    client = _client(args)
    try:
        rec = state.load(args.id, root)
        pod_id = rec["pod_id"]
    except FileNotFoundError:
        # An id that is really a pod id: `ls` prints those for orphans.
        rec, pod_id = None, args.id
    print("terminating pod %s ..." % pod_id)
    try:
        client.terminate_pod(pod_id)
    except api.PodApiError as e:
        if not api.is_gone(e):
            print("TERMINATE FAILED: %s" % api.redact(str(e))[:300])
            print("THE POD MAY STILL BE BILLING. Check the RunPod console.")
            return 1
        # 404: the pod was terminated elsewhere. That is the outcome `down`
        # was asked for, so the record must say so -- leaving it `running`
        # is what made session 20260909-194107 un-releasable.
        if rec:
            state.mark(args.id, "terminated", root,
                       finished_because="absent-from-account")
        print("no such pod on the account -- it was already terminated. "
              "Nothing is billing." + (" The record is marked terminated."
                                       if rec else ""))
        return 0
    if rec:
        state.mark(args.id, "terminated", root, finished_because="down")
    print("terminated. No confirmation was asked for: DELETE only ever stops "
          "the meter.")
    return 0


# ---------------------------------------------------------------- watch
def cmd_watch(args):
    """Poll until DONE or the cap, then fetch and terminate.

    This is the unattended half of a session, and it is unattended precisely
    because everything it does either costs nothing or saves money.
    """
    root = _repo_root()
    rec = state.load(args.id, root)
    client = _client(args)
    caps = rec.get("caps", {})
    max_hours = float(caps.get("max_hours", 0) or 0)
    max_usd = float(caps.get("max_usd", 0) or 0)
    marker = rec.get("done_marker", "DONE")
    rate = state.effective_rate(rec)
    stall_minutes = float(args.stall_minutes if args.stall_minutes is not None
                          else rec.get("stall_minutes") or 15)
    print("watching %s (pod %s), cap %g h / $%.2f at $%s/hr, stall %g min, "
          "poll %ds" % (rec["id"], rec["pod_id"], max_hours, max_usd,
                        ("%.2f" % rate) if rate else "?", stall_minutes,
                        args.interval))

    last_size, last_growth = None, time.time()

    while True:
        h = state.elapsed_hours(rec)
        try:
            pod = client.get_pod(rec["pod_id"])
        except api.PodApiError as e:
            print("pod is gone: %s" % api.redact(str(e))[:200])
            state.mark(args.id, "terminated", root)
            return 0

        if pod.get("desiredStatus") != "RUNNING":
            print("pod state is %s; stopping the watch"
                  % pod.get("desiredStatus"))
            state.mark(args.id, "terminated", root)
            return 0

        # If the pod's own price has appeared or moved since the record was
        # written, cost against the truth rather than the estimate.
        true_now = pod_true_rate(pod)
        if true_now and true_now != rec.get("usd_per_hr_true"):
            rec["usd_per_hr_true"] = true_now
            state.mark(args.id, rec.get("state", "running"), root,
                       usd_per_hr_true=true_now)
            rate = true_now

        est = state.cost_so_far(rec)

        if max_hours and h is not None and h >= max_hours:
            print("\nCAP REACHED: %s elapsed >= %g h. Fetching what exists, "
                  "then terminating." % (_fmt_hours(h), max_hours))
            _finish(client, rec, root, args, reason="cap")
            return 0

        # The dollar cap, at the rate actually being charged. In 006b this
        # was enforced only in hours, so a pod at 2.1x the confirmed rate
        # stayed inside max_usd by arithmetic accident.
        if max_usd and est is not None and est >= max_usd:
            print("\nSPEND CAP REACHED: ~$%.2f at $%.2f/hr >= max_usd $%.2f. "
                  "Fetching what exists, then terminating."
                  % (est, rate or 0.0, max_usd))
            _finish(client, rec, root, args, reason="max_usd")
            return 0

        finished = False
        size = None
        try:
            ssh = sshx.PodSsh.from_pod(pod, key_path=args.ssh_key)
            finished = ssh.run_is_finished(rec.get("remote_log"), marker)
            size = ssh.log_size(rec.get("remote_log"))
        except (sshx.SshError, OSError) as e:
            print("  [%s] ssh not ready: %s" % (_fmt_hours(h),
                                                api.redact(str(e))[:100]))

        if finished:
            print("\nDONE seen in %s after %s. Fetching, then terminating."
                  % (rec.get("remote_log"), _fmt_hours(h)))
            _finish(client, rec, root, args, reason="done")
            return 0

        # Stall watchdog. A log that stops growing is a run that stopped
        # doing anything, and a pod with nothing to wait for must not
        # survive. Only *growth* resets the clock; an unreadable log does not,
        # or an ssh outage would keep a dead pod alive indefinitely.
        now = time.time()
        if size is not None and size != last_size:
            last_size, last_growth = size, now
        idle_min = (now - last_growth) / 60.0
        if stall_minutes and idle_min >= stall_minutes:
            print("\nSTALLED: %s has not grown for %.1f min (limit %g). "
                  "Terminating." % (rec.get("remote_log"), idle_min,
                                    stall_minutes))
            _finish(client, rec, root, args, reason="stalled")
            return 0

        print("  [%s] running, ~$%.2f so far, log %s, idle %.1f min"
              % (_fmt_hours(h), est or 0.0,
                 "%d B" % size if size is not None else "absent", idle_min))
        time.sleep(args.interval)


def _finish(client, rec, root, args, reason):
    code = 0
    try:
        pod = client.get_pod(rec["pod_id"])
        ssh = sshx.PodSsh.from_pod(pod, key_path=args.ssh_key)
        code = _fetch_outputs(ssh, rec, root)
    except Exception as e:
        print("fetch failed: %s" % api.redact(str(e))[:300])
        code = 1
    finally:
        # Terminate even if the fetch failed. A pod kept alive to retry a
        # download is a pod billing while nobody is watching; the artifacts
        # are on the network volume, which outlives the pod.
        print("terminating pod %s ..." % rec["pod_id"])
        try:
            client.terminate_pod(rec["pod_id"])
            state.mark(rec["id"], "terminated", root, finished_because=reason)
            print("terminated.")
        except api.PodApiError as e:
            print("TERMINATE FAILED: %s" % api.redact(str(e))[:300])
            print("The pod may still be billing. Terminate it in the RunPod "
                  "console, or `oneground pod down %s`." % rec["pod_id"])
            code = 1
    return code


# ---------------------------------------------------------------- ls
def cmd_ls(args):
    """Every oneground pod on the account, reconciled against local records.

    RunPod has no label primitive, so a pod is ours if its name starts with
    `oneground-session-` or its env carries ONEGROUND_SESSION. Both are set at
    create; matching either survives a rename in the console.
    """
    root = _repo_root()
    client = _client(args)
    pods = client.list_pods()
    records = {r.get("pod_id"): r for r in state.load_all(root)}

    ours, others = [], 0
    for pod in pods:
        sid = _session_label(pod)
        if sid:
            ours.append((sid, pod))
        else:
            others += 1

    if not ours:
        print("0 oneground pods on the account."
              + (" (%d other pod(s) not created by oneground.)" % others
                 if others else ""))
    else:
        print("%d oneground pod(s):" % len(ours))
    now = time.time()
    for sid, pod in ours:
        rec = records.get(pod.get("id"))
        caps = (rec or {}).get("caps", {})
        max_hours = float(caps.get("max_hours", 0) or 0)
        h = state.elapsed_hours(rec, now) if rec else None
        rate = pod.get("costPerHr")
        print()
        print("  session %s" % sid)
        print("    pod      : %s  (%s)" % (pod.get("id"),
                                           pod.get("desiredStatus")))
        print("    name     : %s" % pod.get("name"))
        print("    rate     : %s" % ("$%.2f/hr" % rate if rate else "-"))
        print("    elapsed  : %s" % _fmt_hours(h))
        if rec is None:
            print("    ORPHAN   : no local record under .oneground/sessions/. "
                  "It was created elsewhere, or the record was deleted.")
            print("               oneground pod down %s" % pod.get("id"))
        elif max_hours and h is not None and h > max_hours:
            print("    OVER CAP : %s elapsed, cap is %g h. This pod is "
                  "billing past its own limit." % (_fmt_hours(h), max_hours))
            print("               oneground pod down %s" % sid)

    # Reconcile against every pod on the account, not just the ones `ls`
    # recognised as ours: a pod renamed in the console loses the label but is
    # still there, still billing, and its record must not be closed.
    live, reconciled = _reconcile_live(client, root, pods=pods)
    for r in reconciled:
        print()
        print("  session %s: record said %s, but no such pod is on the "
              "account. Nothing was billing; the record is now marked "
              "terminated." % (r["id"], r.get("state")))
    on_account = {p.get("id") for p in pods if p.get("id")}
    for r in live:
        if r.get("pod_id") not in on_account:
            print()
            print("  session %s: created moments ago and not listed by the "
                  "account yet. Left alone; run `ls` again." % r["id"])
    return 0


def _session_label(pod):
    name = pod.get("name") or ""
    prefix = "oneground-session-"
    if name.startswith(prefix):
        return name[len(prefix):]
    env = pod.get("env") or {}
    return env.get("ONEGROUND_SESSION")


# ---------------------------------------------------------------- parser
def build_parser():
    ap = argparse.ArgumentParser(
        prog="oneground pod",
        description="Agent-driven RunPod sessions. Only `up` can create a "
                    "billable resource, and only after a typed 'y'.")
    ap.add_argument("--timeout", type=int, default=60,
                    help="API request timeout, seconds")
    ap.add_argument("--ssh-key", default=None,
                    help="private key for the pod (default: ssh's own choice)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan", help="resolve a session to a priced plan; "
                                    "creates nothing")
    p.add_argument("spec")
    p.add_argument("--payload", action="store_true",
                   help="also print the POST /pods body `up` would send")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("up", help="the only billable subcommand; prompts")
    p.add_argument("spec")
    p.add_argument("--boot-timeout", type=int, default=600)
    p.add_argument("--ssh-ready-timeout", type=int,
                   default=sshx.READY_TIMEOUT_SECONDS,
                   help="wait this long for sshd after the pod reaches "
                        "RUNNING, retrying with backoff (default %d). RUNNING "
                        "is the container's state, not sshd's."
                        % sshx.READY_TIMEOUT_SECONDS)
    p.add_argument("--log-timeout", type=int, default=180,
                   help="terminate if the run's log has not appeared within "
                        "this many seconds (default 180)")
    p.add_argument("--price-tolerance", type=float, default=0.05,
                   help="terminate if the pod's true rate exceeds the "
                        "confirmed rate by more than this fraction "
                        "(default 0.05)")
    p.set_defaults(func=cmd_up)

    p = sub.add_parser("status", help="state, elapsed, cost, last log lines")
    p.add_argument("id", nargs="?")
    p.add_argument("--lines", type=int, default=20)
    p.add_argument("--no-logs", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("fetch", help="download the session's declared outputs")
    p.add_argument("id")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("down", help="terminate (no confirmation; it only "
                                    "saves money)")
    p.add_argument("id")
    p.set_defaults(func=cmd_down)

    p = sub.add_parser("watch", help="poll to DONE or the cap, then fetch and "
                                     "terminate")
    p.add_argument("id")
    p.add_argument("--interval", type=int, default=60)
    p.add_argument("--stall-minutes", type=float, default=None,
                   help="terminate if the run's log has not grown for this "
                        "long (default: the session's stall_minutes)")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("ls", help="oneground pods on the account; orphans "
                                  "and over-cap pods flagged")
    p.set_defaults(func=cmd_ls)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except api.CreateCallBlocked as e:
        print("BLOCKED: %s" % api.redact(str(e)), file=sys.stderr)
        return 2
    except (api.PodApiError, sessionmod.SessionSpecError, planmod.PlanError,
            sshx.SshError, FileNotFoundError) as e:
        print("error: %s" % api.redact(str(e)), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted. Nothing was created by the interrupt itself; "
              "`oneground pod ls` shows what is running.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
