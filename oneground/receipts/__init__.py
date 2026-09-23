"""Receipts: the bytes a measurement leaves behind.

Two kinds are kept apart everywhere in this project, and this module is where
the distinction is made concrete:

    receipt    re-derivable from the seeds and rules. Two builds from the same
               inputs must produce the same bytes, on any host.
    declared   recorded, not re-derivable: timestamps, library versions, the
               host, the device. Its digest is still checked; a rebuild is not
               expected to reproduce it.

Everything here was moved from `corpora/build_fixture.py` in task 007 with its
logic unchanged. That is not incidental: the smoke fixture's six receipt
artifacts are asserted byte-identical across the move, so a "harmless"
cleanup here would show up as a failed regression rather than as a nicer file.

Two things break byte-stability for JSON on this project's mix of hosts, and
both are handled here rather than by the values:

    float formatting   `round_floats` pins decimals, so a value that is equal
                       prints as equal
    line endings       every writer passes newline="\\n". Task 002 found
                       Windows text-mode CRLF in artifacts that had to hash
                       the same on Windows and Linux.
"""

import hashlib
import importlib.metadata as _md
import json
import os

import numpy as np

MANIFEST_NAME = "MANIFEST.sha256"

# Fixed float precision for every JSON receipt.
FLOAT_DECIMALS = 6

# Written into the package at build time, so an installed wheel can answer
# the same question a checkout can. See `setup.py`.
BUILD_STAMP_NAME = "_build_stamp.json"

# The libraries whose versions go in build_info.json. torch is read separately
# by torch_receipt(), which needs its local version segment (task 003c).
RECEIPT_LIBRARIES = ("numpy", "faiss-cpu", "sentence-transformers", "umap-learn")


def _run_git(args):
    """`git <args>` in the package's own tree, or None if it cannot be run."""
    import subprocess
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        r = subprocess.run(["git"] + list(args), cwd=here,
                           capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        return None, "%s: %s" % (type(e).__name__, e)
    if r.returncode != 0:
        return None, "git %s: exit %s: %s" % (
            " ".join(args), r.returncode,
            r.stderr.decode("utf-8", "replace").strip() or "(no stderr)")
    return r.stdout.decode("utf-8", "replace").strip(), None


def _build_stamp():
    """What `setup.py` recorded at build time, or None."""
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), BUILD_STAMP_NAME)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def producing_version():
    """What produced this artifact: the version, and the commit if knowable.

    Task 033. Every other input to a measurement is recorded -- the seed, the
    pins, the corpus digests, the run-level settings -- and until this the one
    that decides what those inputs *mean* was not. Three tasks paid for it:
    028b dated a commit to work out which code measured a workdir, 028c
    measured one configuration at three revisions to settle the same
    question, and `docs/LIBRARY.md` §2.2 cannot give a card a comparability
    verdict better than couldn't-check without it.

        {"version": "0.1.0",
         "commit": "<40 hex>" | None,
         "dirty": True | False | None,
         "source": "checkout" | "wheel" | "unknown",
         "note": "<why commit is None, when it is>"}

    `commit` is None with a stated reason rather than a guess or a refusal:
    an installed wheel has no git, which task 022 made a first-class case.
    A wheel built by this project's `setup.py` carries a build stamp and
    answers as confidently as a checkout.

    **Only the version and the commit.** Never a branch, a remote, a tag or a
    build path: those name a person's working arrangements rather than the
    code, and the identifier scan exists because that distinction gets lost.
    """
    from .. import __version__

    out = {"version": __version__, "commit": None, "dirty": None,
           "source": "unknown", "note": ""}

    stamp = _build_stamp()
    if stamp:
        out["source"] = "wheel"
        out["commit"] = stamp.get("commit")
        out["dirty"] = stamp.get("dirty")
        if not out["commit"]:
            out["note"] = str(stamp.get("note") or
                              "built without a commit recorded")
        return out

    from ..environment import checkout_root
    if checkout_root(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))) is None:
        out["note"] = ("installed without a build stamp and not a git "
                       "checkout, so no commit can be recorded")
        return out

    commit, problem = _run_git(["rev-parse", "HEAD"])
    if commit is None:
        out["source"] = "checkout"
        out["note"] = "this is a checkout and git could not be asked: %s" % (
            problem,)
        return out
    status, problem = _run_git(["status", "--porcelain"])
    out.update(source="checkout", commit=commit,
               dirty=None if status is None else bool(status.strip()))
    if status is None:
        out["note"] = "the working tree's cleanliness could not be read: %s" % (
            problem,)
    return out


#: The repository root, for turning an absolute path into the repo-relative
#: form every other source string in an artifact already uses.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

PUBLIC_PATH_NOTE = ("recorded relative to the repository root, or as a "
                    "basename when outside it: a receipt does not name the "
                    "filesystem it was produced on")


def public_path(raw, repo_root=None):
    """A path fit to be written into a receipt. Task 043 step 5.

    Repo-relative inside the repository, basename outside: still says WHICH
    file, says nothing about where it lives on anybody's machine.

    WHY THIS IS APPLIED WHERE THE FIELD IS WRITTEN
    ----------------------------------------------
    `report.json` recorded `price_table.path` as the absolute path of the
    checkout that produced it. Task 041's rule: *a receipt field holding a
    machine-local path cannot be published by running the command that
    produces it.*

    It then forced a sanitization at **three separate boundaries in one
    task** -- the teaser exporter, which owned the function; the fixture
    rebuild, which borrowed it and replaced only its note; and a tracked lab
    test fixture, sanitised by hand so it would not fail the identifier scan.
    Each borrowed a function whose own `path_note` named a different caller.

    Sanitising at publish time is what produced three boundaries, and it
    would produce a fourth, because every new consumer of the receipt is a
    new place to remember. **A receipt that never contains the absolute path
    has nothing to sanitise anywhere.** So the transform lives here, beside
    the other receipt helpers, and runs where the field is written.

    The note names the transform, not a caller: the teaser exporter's version
    said "rewritten by the teaser export", which was false for every other
    caller and true only of the first.
    """
    if not raw:
        return raw
    root = repo_root or REPO_ROOT
    native = str(raw).replace("\\", os.sep).replace("/", os.sep)
    try:
        inside = os.path.commonpath([os.path.abspath(native), root]) == root
    except ValueError:                      # different drives on Windows
        inside = False
    return (os.path.relpath(native, root).replace(os.sep, "/")
            if inside else os.path.basename(native))


def public_paths_in(table, keys=("path",), repo_root=None):
    """`table` with each named key made fit to record, and a note saying so."""
    if not table:
        return table
    out = dict(table)
    changed = False
    for key in keys:
        if out.get(key):
            was = out[key]
            out[key] = public_path(was, repo_root)
            changed = changed or out[key] != was
    if changed:
        out["path_note"] = PUBLIC_PATH_NOTE
    return out


def sha256_file(path, buf=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(buf)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def manifest_digest(digests):
    """One sha256 over a `{name: sha256}` mapping of many files.

    A source made of many files has no single byte stream to hash, so its
    receipt is taken over the sorted `<sha256>  <name>` lines instead -- the
    `sha256sum -c` format, so the value can be reproduced with shell tools.
    The digest moves if any file's bytes change, if one is added or removed,
    or if one is renamed, which is everything `source.snapshot_sha256` is for.

    Shared so that a source read from disk and the same source read over the
    network cannot disagree about their own digest: both build the manifest
    here.
    """
    lines = sorted(f"{sha}  {name}" for name, sha in digests.items())
    return hashlib.sha256(
        "".join(f"{line}\n" for line in lines).encode()).hexdigest()


def sha256_array(a):
    """Digest of an array's raw bytes.

    Deliberately not the same as `sha256_file` of the .npy holding it: the file
    digest covers numpy's header too. The fixture spec publishes array digests
    for `vectors`/`queries`/`ground_truth` and file digests for everything
    else, and MANIFEST.sha256 is always file digests. Confusing the two makes
    a correct artifact look wrong.
    """
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def round_floats(obj, nd=FLOAT_DECIMALS):
    """Fixed float precision, so a value that is equal prints as equal.

    Counts stay integers. bool is checked before int because it is a subclass.
    """
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, np.floating):
        return round(float(obj), nd)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, dict):
        return {k: round_floats(v, nd) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [round_floats(v, nd) for v in obj]
    return obj


def write_json_stable(path, obj):
    """Sorted keys and LF newlines, so the bytes do not depend on dict order
    or on the host's line-ending convention (a Windows build and a Linux build
    of the same fixture must agree byte for byte)."""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=2, sort_keys=True, ensure_ascii=True)
        f.write("\n")


def write_manifest(outdir, files):
    """Digest every listed file that exists. LF-pinned, for the same reason as
    write_json_stable(). Returns the names actually written."""
    written = []
    with open(os.path.join(outdir, MANIFEST_NAME), "w",
              encoding="utf-8", newline="\n") as m:
        for fn in files:
            fp = os.path.join(outdir, fn)
            if os.path.exists(fp):
                m.write(f"{sha256_file(fp)}  {fn}\n")
                written.append(fn)
    return written


def append_manifest(outdir, fn):
    """Append one digest line. Used for the projection, which is produced after
    the manifest is written."""
    with open(os.path.join(outdir, MANIFEST_NAME), "a",
              encoding="utf-8", newline="\n") as m:
        m.write(f"{sha256_file(os.path.join(outdir, fn))}  {fn}\n")


def installed(pkg):
    try:
        _md.version(pkg)
        return True
    except _md.PackageNotFoundError:
        return False


def library_versions(packages=RECEIPT_LIBRARIES, log=None):
    """Versions of the libraries that produced a measurement, plus torch.

    torch is appended through `torch_receipt` rather than importlib.metadata,
    for the reason given there.
    """
    versions = {p: _md.version(p) for p in packages if installed(p)}
    info = torch_receipt(log=log)
    if info["torch"]:
        versions["torch"] = info["torch"]
    return versions, info


def torch_receipt(log=None):
    """torch's identity, for build_info.json.

    torch is what actually produces the vectors, so on a cuda build it is the
    most load-bearing version in the receipt. `torch.__version__` is used in
    preference to importlib.metadata: the metadata drops the local segment,
    reporting "2.14.0" where torch itself reports "2.14.0+cpu" or
    "2.14.0+cu130" -- and that segment is exactly what distinguishes one CUDA
    build from another.

    Read defensively. By the time this runs every artifact is already written,
    so an odd torch install must degrade to a null field, not sink the build.
    """
    def _say(msg):
        if log:
            log(msg)

    info = {"torch": None, "torch_cuda": None, "cuda_device_name": None}
    try:
        import torch
    except Exception as e:                      # pragma: no cover - env-specific
        _say(f"could not read torch version: {e}")
        return info

    info["torch"] = getattr(torch, "__version__", None)
    try:
        info["torch_cuda"] = torch.version.cuda          # None on a CPU build
        if torch.cuda.is_available():
            info["cuda_device_name"] = torch.cuda.get_device_name(0)
    except Exception as e:                      # pragma: no cover - env-specific
        _say(f"could not read cuda details: {e}")
    return info
