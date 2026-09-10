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

# The libraries whose versions go in build_info.json. torch is read separately
# by torch_receipt(), which needs its local version segment (task 003c).
RECEIPT_LIBRARIES = ("numpy", "faiss-cpu", "sentence-transformers", "umap-learn")


def sha256_file(path, buf=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(buf)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


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
