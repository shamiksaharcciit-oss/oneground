"""The pinned-environment guard.

Every command that writes a canonical artifact runs this before it computes
anything, and **refuses** when the interpreter is not running the versions
`requirements.txt` pins.

WHY REFUSE RATHER THAN WARN
---------------------------
Task 013 produced a complete, correct-looking verification of arxiv-150k on
numpy 2.2.6 and faiss 1.14.3, against pins of 2.5.3 and 1.15.0, and printed
"every published value reproduced. This fixture's status may be set to
`verified`." The numbers happened to agree. Nothing in the tooling noticed,
and the fixture's status was one command away from being set on a
reproduction that never happened under the pins.

The cause was not a broken environment. `.venv` had every one of the 65 pins
correct and had done since the day it was created. The cause was that bare
`python` on that machine is the system interpreter, and every command in a
long session used it. A warning would have scrolled past exactly as the
existing per-value notes did.

So: the interpreter path is printed every time, and a mismatch stops the
command. `--allow-unpinned` exists because there are legitimate reasons to run
outside the pins -- a contributor without faiss-cpu built for their platform,
a quick look at a report -- but it is never silent: it stamps the artifact,
and everything downstream can see the stamp.

WHAT COUNTS AS PINNED
---------------------
Only the packages in `PINNED`: the ones whose version changes the numbers.
numpy and faiss decide k-means, HNSW construction and every distance;
scikit-learn decides what it is used for. A different `pyyaml` cannot move a
measurement, and failing a run over it would train people to pass
`--allow-unpinned` by reflex, which is worse than not checking.
"""

import os
import re
import sys

REQUIREMENTS = "requirements.txt"

# The packages whose version can change a measured number. Deliberately short:
# a guard that fires on things that cannot matter gets routed around.
PINNED = ("numpy", "faiss", "faiss-cpu", "scikit-learn")

UNPINNED_NOTE = "unpinned environment"


class UnpinnedEnvironment(RuntimeError):
    """The interpreter is not running the pinned versions."""


def read_requirements_pins(path=REQUIREMENTS):
    """{package: version} from a pinned requirements file.

    Environment markers are stripped: `pywin32==312; sys_platform == "win32"`
    pins 312 on the platform it applies to, and the marker is not part of the
    version.
    """
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.split("#")[0].strip()
            if not line or "==" not in line:
                continue
            name, _, rest = line.partition("==")
            out[_normalise(name)] = rest.split(";")[0].strip()
    return out


def _normalise(name):
    """pip normalises `pydantic_core` and `pydantic-core` to the same project.

    Comparing the raw strings reports a package as absent that is installed,
    which is how task 013's first freeze comparison produced a false negative.
    """
    return str(name).strip().lower().replace("_", "-")


def running_versions():
    """What *this* process actually imported. Never what it was asked to."""
    out = {}
    try:
        import numpy
        out["numpy"] = numpy.__version__
    except ImportError:                                   # pragma: no cover
        pass
    try:
        import faiss
        # requirements.txt pins the distribution (faiss-cpu); the module
        # reports the same version under either name, so both are recorded
        # and whichever the file pins is the one compared.
        out["faiss"] = faiss.__version__
        out["faiss-cpu"] = faiss.__version__
    except ImportError:                                   # pragma: no cover
        pass
    try:
        import sklearn
        out["scikit-learn"] = sklearn.__version__
    except ImportError:                                   # pragma: no cover
        pass
    return out


def running_pin_mismatches(requirements_path=REQUIREMENTS, versions=None,
                           pinned=None):
    """[(package, running, pinned)] for the environment doing the work.

    This is the comparison that decides whether an artifact may be called
    canonical. Comparing a recorded `build_info` against `requirements.txt`
    answers a different question -- whether some past build was pinned -- and
    says nothing about the process running now.

    `pinned` is a `{package: version}` to compare against instead of reading
    `requirements_path`. Task 022: outside a checkout there is no
    requirements.txt, and the installed distribution's own pins are the set.
    """
    if pinned is None:
        pinned = read_requirements_pins(requirements_path)
    else:
        pinned = {_normalise(k): v for k, v in pinned.items()}
    have = {_normalise(k): v for k, v in
            (running_versions() if versions is None else versions).items()}
    out = []
    for name in PINNED:
        want, got = pinned.get(_normalise(name)), have.get(_normalise(name))
        if want is None or got is None:
            continue
        if str(want) != str(got):
            out.append((_normalise(name), got, want))
    return out


def in_venv():
    return sys.prefix != sys.base_prefix


def local_environment_id():
    """`local:<os>-<arch>` -- what a non-pod run is called in an artifact.

    Never `platform.node()`. A hostname identifies a person's machine and
    tells a reader of the artifact nothing they need; the operating system and
    architecture tell them everything the id is for, which is whether two
    measurements were made somewhere comparable.

    `platform.system()` and `platform.machine()` are read defensively for the
    same reason `platform.node()` used to be: on Windows they go through
    `platform.uname()`, whose WMI query has been observed raising under memory
    pressure. An environment id is not worth failing a finished measurement
    over.
    """
    import platform
    try:
        system = (platform.system() or "unknown").lower()
    except Exception:                                 # pragma: no cover - env
        system = "unknown"
    try:
        arch = (platform.machine() or "unknown").lower()
    except Exception:                                 # pragma: no cover - env
        arch = "unknown"
    return f"local:{system}-{arch}"


def environment_id():
    """The pod's id when there is one, else `local:<os>-<arch>`.

    `ONEGROUND_ENVIRONMENT_ID` is set by the pod runner. A pod id names a
    rented machine that no longer exists; a hostname names a laptop that does.
    """
    eid = os.environ.get("ONEGROUND_ENVIRONMENT_ID")
    return str(eid) if eid else local_environment_id()


def interpreter():
    """What an artifact records about the interpreter that produced it.

    Deliberately without `sys.executable` or `sys.prefix`: those are absolute
    paths through someone's home directory, they are generated at run time so
    no redaction pass can reach them, and they answer no question a reader of
    a published artifact has. `describe()` still prints the full path to the
    terminal, where it is the whole point.
    """
    return {
        "environment_id": environment_id(),
        "python_version": ".".join(str(v) for v in sys.version_info[:3]),
        "in_venv": in_venv(),
    }


def stamp(requirements_path=REQUIREMENTS, allowed_unpinned=False):
    """The environment block written into build_info and the report footer.

    `pinned` is the field everything downstream reads. When it is false the
    artifact was produced outside the pins and says so in its own bytes, which
    is the point of `--allow-unpinned` being a stamp rather than a shrug.
    """
    bad = running_pin_mismatches(requirements_path)
    out = dict(interpreter())
    out["pinned"] = not bad
    out["versions"] = running_versions()
    # The file name, not its absolute path: which requirements file was
    # honoured is worth recording, where it sat on one machine is not.
    out["requirements"] = os.path.basename(requirements_path) \
        if os.path.exists(requirements_path) else None
    if bad:
        out["mismatches"] = [{"package": n, "running": g, "pinned": w}
                             for n, g, w in bad]
        out["note"] = UNPINNED_NOTE
        out["allowed_by"] = "--allow-unpinned" if allowed_unpinned else None
    return out


# ------------------------------------------------ the package guard (020b)
#
# The same class of mistake as the system interpreter, one level down. Task
# 020 worked in a second `git worktree` of this repository, beside a venv
# with an editable install. That install resolves `oneground` to the checkout
# it was installed from, wherever a command is run. So in the second tree, the
# `oneground` console script -- or any process not started from the tree's
# root -- runs the FIRST checkout's code against the second tree's inputs and
# writes the second tree's outputs: a complete, correct-looking run of code
# nobody is looking at. A test run is exposed the same way: whichever module
# imports `oneground` first decides, for the whole process, which tree is
# under test.
#
# It gets the answer the interpreter got: print both paths, every time, and
# refuse on a mismatch.


class ForeignPackage(RuntimeError):
    """The imported oneground package is not the working tree's own."""


def package_dir():
    """The directory of the `oneground` package this process imported."""
    return os.path.dirname(os.path.abspath(__file__))


def working_tree_root(start=None):
    """The nearest directory at or above `start` holding a `.git`, or None.

    `.git` may be a directory (a clone) or a file (a `git worktree`, whose
    `.git` points back at the shared repository). Both are working trees, and
    the second is where task 020 met this.
    """
    here = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.exists(os.path.join(here, ".git")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def _same_path(a, b):
    return (os.path.normcase(os.path.realpath(a))
            == os.path.normcase(os.path.realpath(b)))


def package_tree_mismatch(cwd=None, package=None):
    """(tree, its_package, imported) when this process runs another tree's
    code; None when it does not, or when there is nothing to judge.

    Judged only inside a oneground checkout: a working tree with its own
    `oneground/__init__.py`. There, the package doing the work must be that
    checkout's own `oneground/`. Anywhere else -- a user's project with
    oneground pip-installed, or no working tree at all -- there is no second
    copy to confuse it with, and nothing is judged.

    Being somewhere under the tree is not enough, and is not what is checked:
    a venv inside the checkout holds an installed copy of the package under
    the tree, and an installed copy is exactly the stale code this stops.
    """
    tree = working_tree_root(cwd)
    if tree is None:
        return None
    own = os.path.join(tree, "oneground")
    if not os.path.isfile(os.path.join(own, "__init__.py")):
        return None
    imported = package_dir() if package is None else package
    if _same_path(imported, own):
        return None
    return tree, own, imported


def guard_package(command, cwd=None, package=None, log=print):
    """Refuse when this process is running another checkout's oneground.

    There is no flag past it. `--allow-unpinned` stamps an artifact made
    under other library versions, and a reader can weigh that stamp; no stamp
    turns a run of one source tree into an artifact of another. The way past
    is to run the tree you mean, which the message says how to do.
    """
    bad = package_tree_mismatch(cwd, package)
    if bad is None:
        return
    tree, own, imported = bad
    for line in (
        "",
        f"REFUSED: `{command}` writes a canonical artifact, and the oneground "
        "package this",
        "process imported is not the one in the working tree it is running "
        "in:",
        "",
        f"    working tree        {tree}",
        f"    its package         {own}",
        f"    package imported    {imported}",
        "",
        "  Every number would be computed by the imported package's code, while",
        "  the inputs and outputs are this tree's. A venv's editable install",
        "  does this without a word: it resolves `oneground` to the checkout it",
        "  was installed from, wherever the command runs.",
        "",
        "  Run this tree's code from this tree's root:",
        "",
        f"      cd {tree}",
        "      <venv python> -m oneground.cli ...",
        "",
        "  There is no flag past this. --allow-unpinned does not apply: it is",
        "  about library versions, and this is about which code is running.",
    ):
        log(line)
    raise ForeignPackage(
        f"{command}: imported {imported}, working tree is {tree}")


def describe(requirements_path=REQUIREMENTS, package=None):
    """What every guarded command prints, whatever the outcome: the
    interpreter (task 013b) and the package it imported (task 020b)."""
    where = "venv" if in_venv() else "SYSTEM INTERPRETER"
    return (f"python  {sys.executable}  ({where})\n"
            f"package {package_dir() if package is None else package}")


def guard(command, requirements_path=REQUIREMENTS, allow_unpinned=False,
          log=print, cwd=None, package=None):
    """Print the interpreter and package; refuse if either is wrong. Returns
    the stamp.

    Raises `ForeignPackage` when the imported package is not the working
    tree's own, and `UnpinnedEnvironment` when the versions differ and
    `allow_unpinned` is false. The caller turns either into an exit code; the
    message is written for someone who has just been stopped and needs to know
    what to type next.
    """
    log(describe(requirements_path, package))
    guard_package(command, cwd, package, log=log)
    bad = running_pin_mismatches(requirements_path)
    if not bad:
        return stamp(requirements_path)

    lines = [
        "",
        f"REFUSED: `{command}` writes a canonical artifact, and this "
        "interpreter is not",
        "running the versions requirements.txt pins:",
        "",
    ]
    for name, got, want in bad:
        lines.append(f"    {name:<16} running {got:<12} pinned {want}")
    lines += [
        "",
        f"    interpreter  {sys.executable}",
        f"    requirements {os.path.abspath(requirements_path)}",
        "",
        "  A measurement computed under different libraries is not the",
        "  measurement the pins describe, and an artifact that does not say so",
        "  is worse than no artifact. Task 013 produced a complete, plausible",
        "  verification this way and came one command from publishing it.",
        "",
    ]
    if not in_venv():
        lines += [
            "  This is the system interpreter. The project's venv is what",
            "  carries the pins:",
            "",
            "      .venv\\Scripts\\python.exe -m oneground ...      (Windows)",
            "      .venv/bin/python -m oneground ...              (POSIX)",
            "",
        ]
    else:
        lines += [
            "  This is a venv, but not one matching the pins. Install them:",
            "",
            f"      python -m pip install -r {requirements_path}",
            "",
        ]
    lines += [
        "  To proceed anyway, pass --allow-unpinned. The artifact is then",
        f"  stamped `{UNPINNED_NOTE}` and every reader of it can see that.",
    ]
    for line in lines:
        log(line)
    raise UnpinnedEnvironment(
        f"{command}: {len(bad)} pinned package(s) differ from "
        f"{requirements_path}")


def guard_or_exit(command, requirements_path=REQUIREMENTS,
                  allow_unpinned=False, log=print, cwd=None, package=None):
    """`guard`, but returns (stamp, exit_code) instead of raising.

    Command handlers use this so a refusal is an ordinary non-zero exit rather
    than a traceback: being stopped by a guard is not a crash.

    The package check runs on both paths, before `allow_unpinned` is
    consulted: that flag answers a question about library versions and must
    not wave through a run of the wrong source tree. `cwd` and `package`
    exist so the check can be tested without a second real checkout.
    """
    try:
        if allow_unpinned:
            log(describe(requirements_path, package))
            guard_package(command, cwd, package, log=log)
            s = stamp(requirements_path, allowed_unpinned=True)
            if not s["pinned"]:
                log("")
                log(f"WARNING: --allow-unpinned. This artifact will be stamped "
                    f"`{UNPINNED_NOTE}`.")
                for m in s["mismatches"]:
                    log(f"    {m['package']:<16} running {m['running']:<12} "
                        f"pinned {m['pinned']}")
                log("")
            return s, 0
        return guard(command, requirements_path, allow_unpinned=False,
                     log=log, cwd=cwd, package=package), 0
    except (UnpinnedEnvironment, ForeignPackage):
        return None, 2


# Every command that has been wrapped in `guarded`. Populated at import time
# by decoration, so it cannot drift from what is actually guarded -- unlike
# the hand-written list task 013b shipped, which a seventh command would have
# silently escaped.
GUARDED_COMMANDS = set()


def guarded(command):
    """Decorate a CLI handler so it runs the guard first and is registered.

    The handler is called as `f(args, rest, env_stamp=...)` when it accepts
    the keyword, and `f(args, rest)` otherwise -- a command that writes no
    stamp should not have to take one.
    """
    import functools
    import inspect

    def decorate(f):
        takes_stamp = "env_stamp" in inspect.signature(f).parameters

        @functools.wraps(f)
        def wrapper(args, rest):
            stamp, code = guard_or_exit(
                command,
                allow_unpinned=getattr(args, "allow_unpinned", False))
            if code:
                return code
            if takes_stamp:
                return f(args, rest, env_stamp=stamp)
            return f(args, rest)

        wrapper.oneground_guarded = command
        GUARDED_COMMANDS.add(command)
        return wrapper

    return decorate


def is_guarded(fn):
    """True when `fn` was wrapped by `guarded`. Used by the coverage test."""
    return getattr(fn, "oneground_guarded", None) is not None


def add_argument(parser):
    """The flag, worded the same everywhere it appears."""
    parser.add_argument(
        "--allow-unpinned", action="store_true",
        help="run even though this interpreter's numpy/faiss/scikit-learn "
             "differ from requirements.txt. The artifact is stamped "
             f"`{UNPINNED_NOTE}`.")


# ----------------------------------------------- the tracked-tree identifier
# scan (task 017)
#
# Task 014 redacted the developer's hostname and home directory out of the
# tree and added guards so they could not come back. Every one of those guards
# asserts on what is about to be WRITTEN -- `stamp()`, the calibration history
# id, and an AST check that no module reaches for `platform.node()`. Nothing
# looked at what was already committed.
#
# Task 015 found the hole the hard way: a branch forked before the redaction
# carried four occurrences of a hostname and a home path back toward the public
# tree through a green suite, and a grep found them rather than a test. Task
# 016 then landed `tasks/016-decision-log.txt` with two absolute developer
# paths in it, onto main, published. Both were invisible for the same reason.
#
# This closes it from the other side: walk what is tracked and read it.

# Account names that identify nobody, so flagging them produces noise instead
# of findings. `runner` is every GitHub Actions job's username and an ordinary
# English word besides; the rest name a role rather than a person.
GENERIC_ACCOUNTS = frozenset({
    "runner", "root", "user", "users", "home", "admin", "administrator",
    "ubuntu", "debian", "docker", "build", "builder", "public", "default",
    "vagrant", "vsts", "azureuser", "github", "actions", "shared", "guest",
    "all users", "defaultuser", "containeradministrator",
})

# Files that quote the trap by name and have to keep doing so. Each entry says
# why: an allowlist nobody can audit is a hole with a comment on it.
IDENTIFIER_SCAN_ALLOWLIST = {
    "oneground/environment.py":
        "this scan; the patterns it looks for are written out here",
    "oneground/test_environment.py":
        "the scan's own tests, which inject the patterns on purpose -- with "
        "SYNTHETIC identifiers (task 018): a probe written with the "
        "developer's own hostname would publish it under cover of the "
        "allowlist, which is the allowlist doing the opposite of its job",
    "tasks/017-hardening.md":
        "the brief commissioning the scan quotes the patterns to specify it",
    "tasks/T3-hosting.report.md":
        "reports the `DESKTOP-` occurrence count from T2b's redaction pass",
}

# A file whose bytes are not text. Reading a .npy as utf-8 finds nothing and
# costs the whole array.
_BINARY_SUFFIXES = (
    ".npy", ".npz", ".h5", ".hdf5", ".parquet", ".png", ".jpg", ".jpeg",
    ".gif", ".ico", ".pdf", ".zip", ".gz", ".tgz", ".zst", ".bin", ".so",
    ".pyd", ".dll", ".exe", ".woff", ".woff2", ".ttf", ".otf",
)

# `C:\Users\<who>`, `/home/<who>`, `/Users/<who>`. Both separators, because
# the paths this is looking for are written on Windows and quoted on Linux.
#
# The captured name excludes `<`, `%`, `$`, `~`, a backtick and a dot-only run,
# so a placeholder -- `C:\Users\<developer>`, `%USERNAME%`, `$HOME`,
# `C:/Users/...` -- does not match at all. That is the point: the redacted form
# is what the docs are supposed to say, and a scan that flagged it would be
# telling people to stop redacting.
_HOME_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]{1,2}Users|/home|/Users)[\\/]{1,2}"
    r"([^\\/\s\"'<>:*?|%$~,)\];`]+)")

# The Windows default hostname shape, which is what the developer's box has.
_DESKTOP_RE = re.compile(r"DESKTOP-[A-Z0-9]{5,}", re.I)


def machine_identifiers():
    """Every string that would identify this machine or the person on it.

    Short and generic values are dropped: they are not identifying, and a scan
    that flags `root` or `runner` teaches people to ignore it.
    """
    import platform
    out = set()
    try:
        node = platform.node()
    except Exception:                                 # pragma: no cover - env
        node = None
    for value in (node, os.environ.get("COMPUTERNAME"),
                  os.environ.get("HOSTNAME"), os.environ.get("USERNAME"),
                  os.environ.get("USER"),
                  os.path.basename(os.path.expanduser("~"))):
        text = str(value).strip().lower() if value else ""
        if len(text) > 3 and text not in GENERIC_ACCOUNTS:
            out.add(text)
    return out


def scan_text(text, identifiers=None):
    """[(line_number, kind, line)] for one file's text.

    Separate from the walk so the rule can be tested on a string rather than
    on whatever happens to be committed today.
    """
    idents = machine_identifiers() if identifiers is None else set(identifiers)
    found = []
    for n, line in enumerate(text.splitlines(), 1):
        # One finding per line. The rules overlap on purpose -- an absolute
        # developer path usually carries the account name too -- and reporting
        # a line twice makes a short list look like a long one.
        kind = None
        for m in _HOME_PATH_RE.finditer(line):
            who = m.group(1)
            if set(who) <= {"."}:       # `C:/Users/...` is an elision
                continue
            if who.lower() not in GENERIC_ACCOUNTS:
                kind = f"home directory of {who!r}"
                break
        if kind is None and _DESKTOP_RE.search(line):
            kind = "DESKTOP- hostname"
        if kind is None:
            low = line.lower()
            for ident in sorted(idents):
                if ident in low:
                    kind = f"machine identifier {ident!r}"
                    break
        if kind is not None:
            found.append((n, kind, line.strip()))
    return found


# ----------------------------------------------- inside archives (task 022b)
#
# The walk below read text and skipped every archive by suffix. The
# stackexchange-150k release tarball -- a public release asset -- carried the
# packing machine's user name, uid and gid in every member header, and the
# scan never looked, because it never opened a .tgz and the asset is not
# tracked anyway. An archive is scanned for what it records about whoever made
# it: the gzip header's stored name and comment, each member's owner ids and
# names, member and link names, pax headers, and the text of small text
# members (a build log is a file like any other).

ARCHIVE_SUFFIXES = (".tgz", ".tar.gz", ".tar")

# Where release assets are kept on a developer's machine: the directory
# `fixture verify` reads by default. Not tracked, so the tree walk cannot see
# it.
DEFAULT_ASSET_DIRS = (os.path.join(os.path.expanduser("~"), "oneground-assets"),)

# Members larger than this are data, not text; reading 460 MB of vectors to
# look for a user name finds nothing and costs the whole array.
_ARCHIVE_TEXT_LIMIT = 1 << 20


def _gzip_header_strings(path):
    """The FNAME and FCOMMENT a gzip header stores (RFC 1952), or []."""
    import struct
    out = []
    with open(path, "rb") as f:
        head = f.read(10)
        if len(head) < 10 or head[:2] != b"\x1f\x8b":
            return out
        flags = head[3]
        if flags & 4:                                 # FEXTRA
            (xlen,) = struct.unpack("<H", f.read(2))
            f.read(xlen)
        for bit, field in ((8, "gzip FNAME"), (16, "gzip FCOMMENT")):
            if flags & bit:
                s = bytearray()
                while True:
                    b = f.read(1)
                    if not b or b == b"\0":
                        break
                    s += b
                out.append((field, s.decode("latin-1")))
    return out


def archive_findings(path, identifiers=None):
    """[(member, kind, detail)] for what one tar archive records about its maker.

    Owner ids other than 0 and owner names other than a generic account are
    findings whoever they belong to: `--owner=0 --group=0 --numeric-owner` is
    the rule, and another person's name would leak just the same. Names, pax
    headers and small text members go through `scan_text`. An archive that
    cannot be read is reported rather than passed -- it was not checked.
    """
    import tarfile
    idents = machine_identifiers() if identifiers is None else set(identifiers)
    out = []
    for field, value in _gzip_header_strings(path):
        for _n, kind, line in scan_text(value, idents):
            out.append(("", kind, f"{field}: {line}"))
    try:
        with tarfile.open(path, "r:*") as t:
            for m in t:
                if m.uid or m.gid:
                    out.append((m.name, "owner id",
                                f"uid {m.uid} gid {m.gid}"))
                for field, value in (("uname", m.uname), ("gname", m.gname)):
                    if value and value.strip().lower() not in GENERIC_ACCOUNTS:
                        out.append((m.name, "owner name",
                                    f"{field} {value!r}"))
                names = [m.name, m.linkname or ""]
                names += [f"{k}={v}" for k, v in (m.pax_headers or {}).items()]
                for text in names:
                    for _n, kind, line in scan_text(text, idents):
                        out.append((m.name, kind, line[:200]))
                if m.isfile() and m.size <= _ARCHIVE_TEXT_LIMIT:
                    raw = t.extractfile(m).read()
                    if b"\0" not in raw[:8192]:
                        for n, kind, line in scan_text(
                                raw.decode("utf-8", "replace"), idents):
                            out.append((f"{m.name}:{n}", kind, line[:200]))
    except (tarfile.TarError, OSError, EOFError) as e:
        out.append(("", "unreadable archive, not checked",
                    f"{type(e).__name__}: {e}"))
    return out


def asset_archive_findings(dirs=None, identifiers=None):
    """[(archive path, member, kind, detail)] for every archive in the asset dirs.

    None when none of the directories exists: nothing was scanned, which is not
    the same answer as "scanned and clean".
    """
    dirs = DEFAULT_ASSET_DIRS if dirs is None else dirs
    existing = [d for d in dirs if os.path.isdir(d)]
    if not existing:
        return None
    idents = machine_identifiers() if identifiers is None else identifiers
    out = []
    for d in existing:
        for dirpath, _dirnames, filenames in os.walk(d):
            for name in sorted(filenames):
                if name.lower().endswith(ARCHIVE_SUFFIXES):
                    p = os.path.join(dirpath, name)
                    for member, kind, detail in archive_findings(p, idents):
                        out.append((p, member, kind, detail))
    return out


class GitUnavailable(RuntimeError):
    """There is a checkout to scan, and git could not be asked what is in it.

    Distinct from "not a checkout". Task 022e: both were reported as None, so
    a tree with a `.git` and no runnable git skipped the identifier scan with
    "nothing to scan" -- green, having read nothing, which is the failure the
    scan exists to catch.
    """


def checkout_root(start=None):
    """The nearest directory at or above `start` holding a `.git`, else None.

    A `.git` is a directory in a checkout and a file in a worktree or a
    submodule; either answers "there is a tree here that git could describe".
    Walks upward because a command may run from a subdirectory.
    """
    d = os.path.abspath(start or ".")
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def tracked_files(root=None):
    """Every path `git ls-files` reports, or None when this is not a checkout.

    None rather than an empty list: "there are no tracked files" and "this is
    not a checkout" are different answers, and only one of them means the scan
    checked something.

    Raises `GitUnavailable` when a `.git` is there but git could not answer --
    not on PATH, or failing. The caller must not read that as a clean tree.
    """
    import subprocess
    cmd = ["git", "ls-files", "-z"]
    cwd = root or "."
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        _raise_if_checkout(cmd, cwd, f"{type(e).__name__}: {e}")
        return None
    if r.returncode != 0:
        _raise_if_checkout(cmd, cwd, "exit %s: %s" % (
            r.returncode,
            r.stderr.decode("utf-8", "replace").strip() or "(no stderr)"))
        return None
    return [p for p in r.stdout.decode("utf-8", "replace").split("\0") if p]


def _relative(path):
    """`path` relative to the working directory: an absolute one would put a
    home directory, and so a user name, into a message people paste around."""
    try:
        return os.path.relpath(path)
    except ValueError:                     # pragma: no cover - another drive
        return os.path.basename(os.path.normpath(path)) or path


def _raise_if_checkout(cmd, cwd, detail):
    """Raise `GitUnavailable` naming the command and the error, if there is a
    `.git` at or above `cwd`; otherwise return, so the caller reports None."""
    found = checkout_root(cwd)
    if found is None:
        return
    raise GitUnavailable(
        "%s in %r failed, and %r holds a .git: %s. A scan that reads nothing "
        "is not a clean scan."
        % (" ".join(cmd), _relative(cwd), _relative(found), detail))


def identifier_findings(root=None, allowlist=None):
    """Scan the tracked tree. [(path, line_number, kind, line)], newest rule.

    Returns an empty list when the tree is clean and a populated one when it
    is not; a finding is left to the caller so the same function can be used
    to print a list as to fail a test. None when this is not a checkout, and
    `GitUnavailable` when it is one and git could not be asked.
    """
    allow = IDENTIFIER_SCAN_ALLOWLIST if allowlist is None else allowlist
    paths = tracked_files(root)
    if paths is None:
        return None
    idents = machine_identifiers()
    out = []
    for rel in paths:
        if rel.replace("\\", "/") in allow:
            continue
        full = os.path.join(root or ".", rel)
        if rel.lower().endswith(ARCHIVE_SUFFIXES):
            # Task 022b: opened, not skipped. `smoke-small.tgz` is tracked.
            for member, kind, detail in archive_findings(full, idents):
                out.append((rel.replace("\\", "/") + "!" + member, 0, kind,
                            detail))
            continue
        if rel.lower().endswith(_BINARY_SUFFIXES):
            continue
        try:
            with open(full, "rb") as f:
                raw = f.read()
        except OSError:
            continue                    # deleted or unreadable; not a finding
        if b"\0" in raw[:8192]:
            continue                    # binary without a telling suffix
        text = raw.decode("utf-8", "replace")
        for n, kind, line in scan_text(text, idents):
            out.append((rel.replace("\\", "/"), n, kind, line[:200]))
    return out
