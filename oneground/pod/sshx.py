"""Repo sync, remote exec, log tail and file fetch -- all over SSH.

Why SSH and not `runpodctl`
---------------------------
The brief asks for one of the two, with a justification. It is SSH, on four
counts:

1.  `runpodctl` is not installed on this machine (checked), so choosing it
    would add a binary dependency to a project that pins everything.
2.  `runpodctl send` / `receive` is a one-shot peer-to-peer transfer keyed by
    a short code that a human reads off one terminal and types into another.
    That is fine for a person moving one file and unusable for `watch`, which
    is by definition the unattended path.
3.  Three of the four things a session needs are not transfers at all --
    starting the run under `nohup`, tailing its log, and polling for the DONE
    marker. Those need a shell either way, and RunPod's REST API has no pod-log
    endpoint (its OpenAPI document lists 23 paths; none of them is logs). So
    SSH is required regardless, and adding `runpodctl` would mean two channels
    where one does.
4.  The developer already has an ed25519 key at ~/.ssh/id_ed25519.pub, and
    `ssh`/`scp` are present on this machine.

The repo reaches the pod as a **git bundle**, exactly as POD_SETUP.md has done
by hand since task 002: `git bundle create --all` is one file, needs no
credentials on the pod, and carries history rather than a working-tree copy --
which is also what keeps `run_arxiv_150k.sh` at LF line endings (task 002's
CRLF trap; `.gitattributes` pins it, and cloning from a bundle honours that,
where an scp of the working tree would not).

Note the consequence, first written down in the task 002 report: a bundle
carries **commits, not the working tree**, so anything uncommitted does not
reach the pod. `bundle_repo()` warns when the tree is dirty rather than
silently shipping something older than what the developer is looking at.
"""

import os
import shlex
import subprocess
import tarfile
import tempfile

SSH_OPTS = [
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "UserKnownHostsFile=" + os.path.join(
        os.path.expanduser("~"), ".ssh", "known_hosts"),
    "-o", "ServerAliveInterval=30",
    "-o", "ServerAliveCountMax=3",
    # A connection that cannot be established must fail in seconds rather than
    # sit until the caller's timeout. `up` runs with a pod billing behind it.
    "-o", "ConnectTimeout=30",
    # No prompts, ever. Without this, an ssh that wants a password or a
    # passphrase blocks on a terminal that nobody is watching -- and blocks
    # for the whole of the caller's timeout, which is indistinguishable from a
    # network hang in the error message.
    "-o", "BatchMode=yes",
]

# What a transfer's timeout is made of. The fixed part is the handshake and
# the remote's own work; the rate is a floor, not an estimate -- it is chosen
# low enough that hitting the timeout means something is wrong rather than
# slow.
TRANSFER_BASE_SECONDS = 120
TRANSFER_FLOOR_BYTES_PER_SECOND = 256 * 1024
TRANSFER_MAX_SECONDS = 3600


def transfer_timeout(nbytes):
    """Seconds to allow for moving `nbytes`, from the constants above."""
    return min(TRANSFER_MAX_SECONDS,
               TRANSFER_BASE_SECONDS
               + int(nbytes) / float(TRANSFER_FLOOR_BYTES_PER_SECOND))


class SshError(RuntimeError):
    """A remote command or transfer failed.

    Carries the full stdout and stderr, not only the message. Session
    20260911-001111 reported `git clone exited 1 during Updating files:
    31% (119/381)` and the real error -- a `git checkout` of a branch that
    no longer existed -- was gone, because the message kept the first 800
    characters of a stream whose first 800 characters are always progress.
    """

    def __init__(self, message, returncode=None, stdout="", stderr="",
                 command=""):
        super().__init__(message)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.command = command


class LaunchFailed(SshError):
    """The remote launch returned non-zero, or did not confirm it started.

    Carries the exit code and both streams so the session record can hold what
    actually happened rather than "it did not work".
    """

    def __init__(self, message, returncode=None, stdout="", stderr=""):
        super().__init__(message)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def as_dict(self):
        return {"returncode": self.returncode, "stdout": self.stdout,
                "stderr": self.stderr}


class PodSsh:
    """SSH endpoint for one pod.

    RunPod gives a direct endpoint when the pod requests port 22 and a public
    IP: `publicIp` plus the host port that maps to container port 22, which is
    in `portMappings`.
    """

    def __init__(self, host, port, user="root", key_path=None, timeout=600):
        self.host = host
        self.port = int(port)
        self.user = user
        self.key_path = key_path
        self.timeout = timeout

    @classmethod
    def from_pod(cls, pod, **kw):
        ip = pod.get("publicIp")
        mappings = pod.get("portMappings") or {}
        port = mappings.get("22") or mappings.get(22)
        if not ip or not port:
            raise SshError(
                "pod %s has no SSH endpoint yet (publicIp=%r, 22->%r). A pod "
                "needs ports ['22/tcp'] and supportPublicIp, and the mapping "
                "appears a few seconds after it reaches RUNNING."
                % (pod.get("id"), ip, port))
        return cls(ip, port, **kw)

    # -- plumbing -----------------------------------------------------------
    def _base(self, binary):
        cmd = [binary]
        cmd += ["-P" if binary == "scp" else "-p", str(self.port)]
        if self.key_path:
            cmd += ["-i", self.key_path]
        cmd += SSH_OPTS
        return cmd

    def _run(self, cmd, timeout=None, check=True):
        try:
            # encoding/errors are explicit, not left to the locale. Without
            # them Python decodes with the console codepage -- cp1252 on this
            # machine -- and pip's progress output contains bytes that are not
            # valid cp1252. That killed the reader thread mid-transfer with
            # `UnicodeDecodeError: 'charmap' codec can't decode byte 0x81`
            # during task 006b's first live session. Remote output is UTF-8;
            # errors="replace" means a stray byte mangles one character in a
            # log line instead of crashing a session that is costing money.
            p = subprocess.run(cmd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace",
                               timeout=timeout or self.timeout)
        except subprocess.TimeoutExpired as e:
            # Keep whatever the command managed to say. Session 20260909-202938
            # timed out here and left nothing to diagnose but the port number.
            out = (e.stdout or "") if isinstance(e.stdout, str) else ""
            err = (e.stderr or "") if isinstance(e.stderr, str) else ""
            detail = ""
            if out.strip():
                detail += "\n  stdout: %s" % out.strip()[-400:]
            if err.strip():
                detail += "\n  stderr: %s" % err.strip()[-400:]
            if not detail:
                detail = "\n  (the command wrote nothing before the timeout)"
            raise SshError("timed out after %gs: %s%s"
                           % (timeout or self.timeout,
                              " ".join(cmd[:3]), detail)) from None
        if check and p.returncode != 0:
            raise SshError(
                "%s -> exit %d\n%s"
                % (" ".join(cmd[:3]), p.returncode,
                   tail_lines(p.stderr or p.stdout or "",
                              ERROR_TAIL_LINES)),
                returncode=p.returncode, stdout=p.stdout or "",
                stderr=p.stderr or "", command=" ".join(cmd[:3]))
        return p

    def run(self, command, timeout=None, check=True):
        """Run a shell command on the pod, return stdout."""
        cmd = self._base("ssh") + ["%s@%s" % (self.user, self.host), command]
        return self._run(cmd, timeout=timeout, check=check)

    def put(self, local, remote, timeout=None):
        cmd = self._base("scp") + [local, "%s@%s:%s" % (self.user, self.host,
                                                        remote)]
        self._run(cmd, timeout=timeout)
        return remote

    def get(self, remote, local, timeout=None):
        os.makedirs(os.path.dirname(os.path.abspath(local)) or ".",
                    exist_ok=True)
        cmd = self._base("scp") + ["%s@%s:%s" % (self.user, self.host, remote),
                                   local]
        self._run(cmd, timeout=timeout)
        return local

    def exists(self, remote_path):
        p = self.run("test -e %s && echo yes || echo no" % remote_path,
                     check=False)
        return "yes" in (p.stdout or "")

    # -- the session verbs ---------------------------------------------------
    def tail_log(self, remote_log, lines=20):
        p = self.run("tail -n %d %s 2>/dev/null || echo '(no log yet)'"
                     % (int(lines), remote_log), check=False)
        return (p.stdout or "").rstrip("\n")

    def log_size(self, remote_log):
        """Bytes in the run's log, or None if it does not exist yet.

        The stall and no-run watchdogs both key off this: a log that does not
        exist means the run never started, and a log that stops growing means
        it is no longer doing anything. Task 006b's first pod billed for ten
        minutes in the first state and nothing noticed.
        """
        p = self.run("stat -c %%s %s 2>/dev/null || echo none" % remote_log,
                     check=False)
        text = (p.stdout or "").strip().splitlines()
        if not text:
            return None
        last = text[-1].strip()
        if last == "none" or not last.isdigit():
            return None
        return int(last)

    def run_is_finished(self, remote_log, marker="DONE"):
        """True once the marker has been printed.

        Matched at the start of a line so a marker inside a sentence -- "not
        DONE yet" -- does not end the session early.
        """
        p = self.run("grep -c '^%s$' %s 2>/dev/null || echo 0"
                     % (marker, remote_log), check=False)
        try:
            return int((p.stdout or "0").strip().splitlines()[-1]) > 0
        except (ValueError, IndexError):
            return False

    def start_run(self, repo_dir, command, remote_log, env=None):
        """Launch the session command detached, so the SSH channel can close.

        setsid + nohup + </dev/null: the run must survive both this SSH
        session ending and any later `status` call attaching and detaching.

        The command goes through `bash -c`, which is not decoration. `nohup` is
        a binary, not a shell: it execs its first argument. A session `run:`
        that begins with environment assignments -- and the smoke session's
        does, `SPEC=... SOURCE=... bash corpora/run_arxiv_150k.sh` -- makes
        `nohup` try to exec a program literally named `SPEC=...`, which fails
        with

            nohup: failed to run command 'SPEC=fixtures/arxiv-smoke...':
            No such file or directory

        The pod then sits idle and billing while `watch` waits for a DONE that
        can never come. That is exactly what happened on the first live
        session (task 006b); `build_start_command` is unit-tested against it.
        """
        # A short, explicit timeout. Launching a detached process should take
        # under a second; inheriting the 600 s default meant the first live
        # session spent ten minutes billing while this call hung, and only then
        # reported a failure that had already happened. If the launch does not
        # come back in a minute, something is wrong and the pod should be
        # handed back to the caller to terminate, not waited on.
        p = self.run(build_start_command(repo_dir, command, remote_log, env),
                     timeout=60, check=False)
        out = (p.stdout or "").strip()
        err = (p.stderr or "").strip()

        # The launch either says so or it did not happen. Task 011's session
        # 20260909-184937 took a bare `echo $!` as proof and waited three
        # minutes on a run that had never started; a pid on stdout is not
        # evidence that anything is running.
        launched = "ONEGROUND_LAUNCHED" in out
        if p.returncode != 0 or not launched:
            raise LaunchFailed(
                "the remote launch did not start the run.\n"
                f"  exit code : {p.returncode}\n"
                f"  stdout    : {out or '(empty)'}\n"
                f"  stderr    : {err or '(empty)'}\n"
                f"  command   : {command}\n"
                f"  log       : {remote_log}",
                returncode=p.returncode, stdout=out, stderr=err)

        pid = out.split("ONEGROUND_LAUNCHED", 1)[1].strip().split()[0] \
            if "ONEGROUND_LAUNCHED" in out else ""
        return {"pid": pid, "stdout": out, "stderr": err,
                "returncode": p.returncode, "launched": True}


def build_start_command(repo_dir, command, remote_log, env=None):
    """The remote line that launches a session command detached.

    Split out from `start_run` so it can be tested without a pod -- the bugs it
    exists to prevent have each cost a live session and none could be caught by
    a test that needed one.

    Two things it must get right, both learned the hard way:

    **`bash -c`, not `nohup` directly.** `nohup` execs its first argument, so a
    `run:` beginning with `VAR=value` made it try to exec a program called
    `SPEC=...` (task 006b).

    **`;` between the setup steps, not `&&`.** `&` binds *looser* than `&&`, so

        mkdir -p D && setsid nohup bash -c P > LOG 2>&1 < /dev/null & echo $!

    does not mean "mkdir, then background the launch". It means "background the
    whole (mkdir && launch) list, then echo" -- `jobs -l` shows one job for the
    entire list, and `$!` is that subshell's pid, not the run's. ssh then
    returns as soon as `echo` finishes and sshd tears the session down, so the
    subshell can take SIGHUP *before* it ever reaches the redirect. The caller
    gets a plausible pid, no log is ever created, and the no-run watchdog
    terminates a pod that never started anything (task 011, session
    20260909-184937: "pid 361", log absent after 180 s).

    So the setup runs in the foreground, the log is created **synchronously**
    before anything is backgrounded -- its existence must never depend on a
    race -- and only the setsid'd run is put in the background.
    """
    # The run carries its own environment rather than trusting the pod's.
    #
    # RunPod's `env` is set for the container's main process. `oneground pod`
    # launches the run over ssh, and sshd hands out a fresh shell that never
    # inherits it -- so in session 20260909-194107 every ONEGROUND_* value was
    # a default and the smoke pod ran the arXiv requirements at the wrong load
    # profile. `up` already knows the session's env locally, so it exports it
    # into the payload and the run stops depending on how the image wires
    # sshd.
    exports = "".join(
        "export %s=%s; " % (k, shlex.quote(str(v)))
        for k, v in sorted((env or {}).items()))
    payload = "cd %s && %s%s" % (shlex.quote(repo_dir), exports, command)
    log = shlex.quote(remote_log)
    return (
        # Foreground, in order, each failing loudly:
        "mkdir -p $(dirname {log}) || {{ echo 'ONEGROUND_LAUNCH_FAIL mkdir' >&2; exit 11; }}; "
        ": > {log} || {{ echo 'ONEGROUND_LAUNCH_FAIL create-log' >&2; exit 12; }}; "
        # setsid puts the run in its own session so a SIGHUP to the ssh
        # session cannot reach it. It is hardening, not a requirement: nohup
        # alone already ignores HUP, and a shell without setsid (Git Bash, and
        # some minimal images) must still be able to launch. Which one was
        # used is reported, so a run that got the weaker form is visible.
        "if command -v setsid >/dev/null 2>&1; then ONEGROUND_LAUNCHER=setsid; "
        "else ONEGROUND_LAUNCHER=; fi; "
        # Only the run is backgrounded. `&` terminates this command, so the
        # commands after it are separate foreground commands rather than part
        # of the backgrounded list -- which is the bug this whole shape exists
        # to avoid.
        "$ONEGROUND_LAUNCHER nohup bash -c {payload} >> {log} 2>&1 < /dev/null & "
        "ONEGROUND_PID=$!; "
        # Prove the launch actually took: a pid that is not alive a moment
        # later never ran, and saying so here beats a watchdog finding out in
        # three minutes.
        "sleep 0.3; "
        "if kill -0 $ONEGROUND_PID 2>/dev/null || [ -s {log} ]; then "
        "echo ONEGROUND_LAUNCHED $ONEGROUND_PID setsid=${{ONEGROUND_LAUNCHER:-none}}; else "
        "echo 'ONEGROUND_LAUNCH_FAIL not-running' >&2; exit 14; fi"
    ).format(log=log, payload=shlex.quote(payload))


# How many lines of a failed command's output go in the exception message.
# The full text is on the exception and in the session record; this is only
# what a human sees first.
ERROR_TAIL_LINES = 20


def tail_lines(text, n=ERROR_TAIL_LINES):
    """The last `n` meaningful lines, with carriage-return progress collapsed.

    Written after session 20260911-001111. Two things were wrong with the old
    `[:800]`:

    **It took the head.** The useful part of a failed command is its end. The
    first 800 characters of a git clone are always progress.

    **It did not collapse carriage returns.** Git writes progress as one
    enormous line -- `Updating files: 1% ... 100%` separated by carriage
    returns, no newlines -- so 800 characters is a few percent of a single
    line and the cut lands mid-word. That is why the captured output ended at
    `Upda`: not a crash mid-write, a slice through a progress line.

    Each carriage-return run is reduced to its final state, which is what a
    terminal would have shown, and blank fragments are dropped.
    """
    if not text:
        return ""
    out = []
    for raw in str(text).split("\n"):
        frag = raw.split("\r")[-1].rstrip()
        if frag:
            out.append(frag)
    return "\n".join(out[-int(n):])


def head_commit(repo_root="."):
    """(commit, branch) of the tree being bundled.

    The pod must run *this* commit. Recorded at bundle time and checked on the
    pod, because "the pod ran code you did not expect" is a failure that
    produces measurements rather than errors.
    """
    def git(*args):
        p = subprocess.run(["git", "-C", repo_root, *args],
                           capture_output=True, text=True)
        return (p.stdout or "").strip() if p.returncode == 0 else ""
    return git("rev-parse", "HEAD"), git("rev-parse", "--abbrev-ref", "HEAD")


def bundle_repo(repo_root=".", out_path=None):
    """`git bundle create --all`, and warn if the working tree is dirty.

    Returns (bundle_path, uncommitted_paths), covering **modified tracked
    files and untracked ones alike**. A bundle carries commits, so anything
    uncommitted will not reach the pod -- the caller decides whether that is
    acceptable, but it is never silent.
    """
    out_path = out_path or os.path.join(repo_root, "oneground.bundle")
    status = subprocess.run(["git", "-C", repo_root, "status", "--porcelain"],
                            capture_output=True, text=True)
    lines = [ln for ln in (status.stdout or "").splitlines() if ln.strip()]
    # Both halves matter, and task 011 learned the second one the hard way.
    # The original warning listed only modified *tracked* files, so a brand
    # new file -- the very thing a new task adds -- reached the pod silently
    # and the session failed on a missing script after the pod was already
    # billing. Untracked files are the more dangerous case, not the lesser.
    dirty = [ln for ln in lines if not ln.startswith("??")]
    untracked = [ln for ln in lines if ln.startswith("??")]
    p = subprocess.run(["git", "-C", repo_root, "bundle", "create", out_path,
                        "--all"], capture_output=True, text=True)
    if p.returncode != 0:
        raise SshError("git bundle failed: %s" % (p.stderr or p.stdout)[:500])
    return out_path, dirty + untracked


def tar_directory(local_dir, out_path=None):
    """Gzip a directory's *contents* into one archive; return (path, names).

    Contents rather than the directory itself, so the remote side extracts
    with `-C <dest>` and there is no --strip-components count to get wrong.
    """
    if out_path is None:
        fd, out_path = tempfile.mkstemp(prefix="oneground-input-", suffix=".tgz")
        os.close(fd)
    names = sorted(os.listdir(local_dir))
    with tarfile.open(out_path, "w:gz") as tf:
        for name in names:
            tf.add(os.path.join(local_dir, name), arcname=name)
    return out_path, names


def tar_to_absolute_paths(pairs, out_path=None, on_file=None):
    """Pack (local, remote_absolute) pairs into one archive rooted at `/`.

    Each member's name is its remote path with the leading slash removed, so
    the pod extracts the whole set with a single `tar -xzf ... -C /` and every
    file lands exactly where the spec said -- no per-file mkdir, no
    --strip-components, and one connection instead of two per file.

    `on_file(local, remote, nbytes)` is called as each file is added, which is
    what gives the caller per-file progress for a single-archive transfer.
    Returns (archive_path, total_uncompressed_bytes, file_count).
    """
    if out_path is None:
        fd, out_path = tempfile.mkstemp(prefix="oneground-inputs-",
                                        suffix=".tgz")
        os.close(fd)
    total, count = 0, 0
    with tarfile.open(out_path, "w:gz") as tf:
        for local, remote in pairs:
            if not remote.startswith("/"):
                raise SshError("input remote must be absolute: %r" % remote)
            arc_root = remote.lstrip("/")
            if os.path.isdir(local):
                for dirpath, _dirnames, filenames in os.walk(local):
                    for name in sorted(filenames):
                        full = os.path.join(dirpath, name)
                        rel = os.path.relpath(full, local).replace(os.sep, "/")
                        size = os.path.getsize(full)
                        tf.add(full, arcname=arc_root + "/" + rel)
                        total += size
                        count += 1
                        if on_file:
                            on_file(full, remote + "/" + rel, size)
            else:
                size = os.path.getsize(local)
                tf.add(local, arcname=arc_root)
                total += size
                count += 1
                if on_file:
                    on_file(local, remote, size)
    return out_path, total, count


def clone_command(bundle_remote, repo_dir, branch=None, commit=None):
    """The remote shell line that turns an uploaded bundle into a checkout.

    **No branch is checked out by default, and `master` is never assumed.**
    `git clone` from a bundle already checks out the bundle's HEAD, which is
    the commit the operator bundled -- so an extra checkout can only move the
    pod *away* from the code that was meant to run.

    This used to be `git checkout master`, unconditionally and with the branch
    argument never passed by its one caller. Two things were wrong with it:

    1. `master` was renamed `main` in task 014, so the command started failing
       outright -- session 20260911-001111, reported as a clone failure
       because the error was truncated away (see `tail_lines`).
    2. Even while it worked it was wrong. A task branch's session would clone
       the bundle at the task's HEAD and then check out the default branch,
       so the pod measured code the task had not written. Task 015 would have
       run without the pgvector adapter it exists to measure, and the receipt
       would have said nothing.

    `commit`, when given, is asserted after the checkout: the run refuses to
    start on a commit nobody chose. A `git checkout` is still available for a
    caller that genuinely wants a different ref, and it has to ask for it.
    """
    # Free space on the filesystem the clone lands on, BEFORE it starts. The
    # repo is ~47 MB so this has never been the cause, but a checkout that
    # dies part way through looks exactly like a full disk and guessing cost
    # a session once. `dirname` because the directory itself is about to be
    # removed. Note the target is /workspace -- the network volume -- not the
    # container disk, which is the one a reader is likely to assume.
    parts = ['echo "disk before clone:"; df -h "$(dirname {d})" | tail -2'
             .format(d=repo_dir),
             "rm -rf {d}".format(d=repo_dir),
             "git clone {b} {d}".format(b=bundle_remote, d=repo_dir),
             "cd {d}".format(d=repo_dir)]
    if branch:
        parts.append("git checkout {br}".format(br=branch))
    if commit:
        # Printed either way, so the log says which commit the pod is running
        # even when it is the right one.
        parts.append(
            'got="$(git rev-parse HEAD)"; echo "pod repo at $got"; '
            '[ "$got" = "{c}" ] || {{ echo "ERROR: expected {c}" >&2; '
            'exit 1; }}'.format(c=commit))
    else:
        parts.append('echo "pod repo at $(git rev-parse HEAD)"')
    return " && ".join(parts)
