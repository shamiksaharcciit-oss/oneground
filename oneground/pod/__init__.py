"""
oneground pod — agent-driven RunPod sessions
============================================

Every pod session before task 006 was the developer pasting commands from
`corpora/POD_SETUP.md` into a browser terminal. This package makes a session
one command, driven by the build agent, without moving the money boundary.

The money boundary
------------------
The agent may **prepare, dry-run, monitor, fetch and terminate**. Only the
developer's typed `y` at an interactive prompt creates a billable resource.

That is enforced in three independent places, so no single mistake crosses it:

1.  `api.RunPodClient` refuses every billable endpoint (see `BILLABLE`) with
    `CreateCallBlocked` unless `allow_create()` has been called on it.
2.  `allow_create()` takes the token returned by `confirm.ask_to_create()`,
    and that function is the only code in the package that reads stdin. It
    refuses outright when stdin is not a TTY.
3.  `cli` constructs the client for `plan`, `status`, `fetch`, `down`,
    `watch` and `ls` without ever calling `allow_create()`, and
    `test_pod.py` asserts against a recording transport that those
    subcommands emit no billable request.

Why there is no `--yes`
-----------------------
A `--yes` flag would be the whole safety property deleted by one word, and it
would be added for exactly the situation in which it is least safe: an
unattended agent loop that has decided, on its own, to spend money. The value
of the boundary is that it cannot be argued around at 2am by a process with no
budget of its own.

The unattended path this project actually needs is the *back* half of a
session, not the front: `watch` polls a pod that a human already paid for and
terminates it at the cap. Creation stays a human keystroke; teardown, which
only ever saves money, is automatic. So the asymmetry is deliberate — there is
no non-interactive create path, and adding one is a design change, not a
convenience flag.

If a future caller genuinely needs headless creation, the right shape is a
short-lived signed authorization minted by the developer with its own cap and
expiry, not a boolean.

Subcommands
-----------
    plan    <session.yaml>   resolve a spec to a concrete plan + live price
    up      <session.yaml>   the only billable path; prompts, reads stdin
    status  [<id>]           state, elapsed, cost so far, last log lines
    fetch   <id>             download the session's declared outputs
    down    <id>             terminate (no confirmation; it only saves money)
    watch   <id>             poll -> DONE or cap -> fetch -> terminate
    ls                       every oneground-labelled pod, orphans flagged

The API key is read from `RUNPOD_API_KEY` in the environment only. It is never
written to disk, never logged, and `api.redact()` scrubs it from every error
string this package raises or prints.
"""

__all__ = ["api", "cli", "confirm", "plan", "session", "sshx", "state"]
