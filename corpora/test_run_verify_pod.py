"""The pod script's control flow, executed rather than eyeballed. Task 017b.

WHY THIS FILE EXISTS
--------------------
`corpora/run_verify_pod.sh` had no test of any kind, and two billed pod
sessions died inside it on the same symptom for two different reasons:

    20260912-171431   the session spec's engine list had drifted, so postgres
                      was never asked for
    20260912-175800   the engine list was fixed, and task 017's baked-image
                      gate turned out to wrap the install AND the start
                      together -- so postgres was present in the image and
                      never started

The second is the one this file is about. It was a one-line mistake in a
shell `if`, it was invisible to `bash -n`, it was invisible to every Python
test, and it cost a pod to find -- twice over, because the first failure
masked it.

WHAT IS TESTED
--------------
The pgvector stanza is extracted from the real script and run under bash with
every command that touches the machine replaced by a stub that records it. So
this asserts what the script DOES -- which commands it reaches, in which
order, under the baked and unbaked images -- without installing postgres.

**Synthetic in its effects, real in its control flow**: nothing here proves
postgres works (task 017 proved that by running the image), only that the
script tries to start it.
"""

import os
import shutil
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "run_verify_pod.sh")

# Words that open a block needing a matching terminator, and their closers.
_OPENERS = {"if": "fi", "for": "done", "while": "done", "until": "done",
            "case": "esac"}


def _bash():
    """A bash that can see this process's filesystem (task 015b's lesson:
    `which bash` finds the WSL launcher from PowerShell, which cannot)."""
    for p in (r"C:\Program Files\Git\bin\bash.exe",
              r"C:\Program Files\Git\usr\bin\bash.exe",
              "/usr/bin/bash", "/bin/bash"):
        if os.path.exists(p):
            return p
    return shutil.which("bash")


def _extract(opening):
    """The block starting at `opening`, up to its matching terminator.

    Only the FIRST word of a line opens or closes a block. Counting every
    token counts the ones inside comments and quoted strings too -- this
    script has plenty of both, and the first version of this helper walked
    off the end of the file looking for a terminator it had already passed.
    """
    with open(SCRIPT, encoding="utf-8") as f:
        lines = f.read().splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() == opening)
    depth, out = 0, []
    for ln in lines[start:]:
        out.append(ln)
        stripped = ln.strip()
        if not stripped or stripped.startswith("#"):
            continue
        head = stripped.split()[0]
        # `if !`, `if [`, `for i`, ... all lead with the keyword.
        if head in _OPENERS:
            depth += 1
        elif head in ("fi", "done", "esac") or head.startswith("fi;"):
            depth -= 1
            if depth == 0:
                return "\n".join(out)
    raise AssertionError("no matching terminator for %r" % opening)


PREAMBLE = r"""
set -uo pipefail
PG_MAJOR=16
PG_PORT=55432
PG_USER=oneground
PG_DB=oneground
PG_CODENAME=noble
PG_VERSION_PIN=16.15-1.pgdg24.04+2
PGVECTOR_VERSION_PIN=0.8.6-1.pgdg24.04+1
PGDATA="$TEST_TMP/pgdata"
PG_LOG="$TEST_TMP/pg.log"
ENGINES="$TEST_ENGINES"
ONEGROUND_BAKED="$TEST_BAKED"
mkdir -p "$PGDATA"
has_engine() { case ",$ENGINES," in *,"$1",*) return 0 ;; *) return 1 ;; esac; }
# Everything that would touch the machine, recorded instead. The point is
# which commands the script REACHES, not what they do.
say() { echo "CALL $*"; }
apt-get()   { say apt-get "$1"; }
apt-cache() { say apt-cache "$1"; }
curl()      { say curl; }
install()   { say install; }
tee()       { cat >/dev/null; say tee; }
chown()     { say chown; }
chmod()     { say chmod; }
date()      { echo 0; }
tail()      { :; }
sleep()     { :; }
# `su postgres -c "<cmd>"` is how every postgres command is invoked. Running
# the inner command against the stub bin is what makes initdb/pg_ctl visible.
su() { shift 2; say su "$*"; eval "$*"; }
"""

_STUBS = ("postgres", "initdb", "pg_ctl", "psql", "createuser", "createdb",
          "pg_isready")


def _run(engines, baked):
    bash = _bash()
    if bash is None:
        pytest.skip("no POSIX shell available")
    body = _extract("if has_engine pgvector; then")
    with tempfile.TemporaryDirectory() as tmp:
        posix_tmp = tmp.replace("\\", "/")
        # Absolute pod paths rewritten into the temp dir: /workspace is the
        # network volume, /usr/lib/postgresql holds the real binaries, and
        # /var/lib/postgresql is root-owned here. Only PATHS are rewritten --
        # no control flow is touched, and control flow is what is under test.
        body = (body
                .replace("/workspace/", posix_tmp + "/")
                .replace("/usr/lib/postgresql/$PG_MAJOR/bin",
                         posix_tmp + "/bin")
                .replace("/var/lib/postgresql", posix_tmp + "/pgsys")
                .replace("/etc/apt", posix_tmp + "/etcapt")
                .replace("/usr/share/postgresql-common/pgdg",
                         posix_tmp + "/pgdgkey"))
        binj = os.path.join(tmp, "bin")
        os.makedirs(binj)
        for name in _STUBS:
            p = os.path.join(binj, name)
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write('#!/bin/sh\necho "CALL %s $*"\nexit 0\n' % name)
            os.chmod(p, 0o755)
        path = os.path.join(tmp, "stanza.sh")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(PREAMBLE
                    + '\nPGBIN="%s/bin"\n' % posix_tmp
                    + body + "\n")
        env = dict(os.environ, TEST_ENGINES=engines, TEST_BAKED=baked,
                   TEST_TMP=posix_tmp)
        r = subprocess.run([bash, path], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120,
                           env=env)
        # The temp dir differs between calls; two runs are only comparable
        # with it normalised out.
        return (r.stdout + r.stderr).replace(posix_tmp, "TMP")


def test_a_baked_image_still_starts_postgres():
    """The bug that cost session 20260912-175800.

    The image ships postgres and pgvector; it does not ship a running server,
    and it deliberately does not ship an initialised PGDATA -- a cluster baked
    at build time would give every pod the same identity. So `initdb` and
    `pg_ctl start` must run whether the image is baked or not. Only the apt
    install is skipped.
    """
    out = _run("qdrant,pgvector", "1")
    assert "skipping apt" in out, out
    assert "initdb" in out, (
        "the baked path never reached initdb -- postgres would be installed "
        "and never started, which is exactly what happened on the pod:\n" + out)
    assert "pg_ctl" in out and "start" in out, out
    # And it really did skip the install.
    assert "CALL apt-get update" not in out, out
    assert "[1/5]" not in out and "[4/5]" not in out, out


def test_an_unbaked_image_reaches_the_install_steps():
    """The unbaked path enters the apt install and announces each step.

    It is NOT driven all the way to `[5/5]` here: the dependency precheck at
    `[3/5]` asks apt what it can resolve, and satisfying that with stubs would
    mean simulating an apt index -- a lot of machinery to assert something the
    real pod sessions have exercised repeatedly. What matters is that the
    baked flag routes into the install rather than past it, which is the
    inverse of the bug.
    """
    out = _run("qdrant,pgvector", "0")
    for step in ("[1/5]", "[2/5]", "[3/5]"):
        assert step in out, (step, out)
    assert "skipping apt" not in out, out


def test_the_server_is_started_in_exactly_one_place():
    """Whatever else the two paths differ on, the server is started the same
    way -- by construction, because there is only one place that starts it.

    An engine started with different flags on the baked path than the unbaked
    one would make a pod row and a laptop row incomparable without either
    being wrong, and the difference would live in a shell script nobody reads.
    One call site makes that impossible rather than unlikely.
    """
    with open(SCRIPT, encoding="utf-8") as f:
        text = f.read()
    starts = [ln for ln in text.splitlines()
              if "pg_ctl" in ln and "-w start" in ln]
    assert len(starts) == 1, starts
    inits = [ln for ln in text.splitlines() if "initdb -D" in ln]
    assert len(inits) == 1, inits


def test_postgres_is_not_touched_when_pgvector_is_not_requested():
    out = _run("qdrant", "1")
    assert "initdb" not in out, out
    assert "skipping apt" not in out, out


def test_the_script_still_parses():
    bash = _bash()
    if bash is None:
        pytest.skip("no POSIX shell available")
    r = subprocess.run([bash, "-n", SCRIPT], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
