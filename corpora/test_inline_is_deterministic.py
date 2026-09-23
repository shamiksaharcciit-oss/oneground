"""`inline.js` depends on the data and nothing else (task 044i, core's find).

**The defect this guards was true of every export this project has ever
sent.** `gzip.compress` writes the current time into the gzip header, so
`inline.js` changed on every export whether or not any data had. That is the
one situation in which a digest stops doing its job: `MANIFEST.sha256`
recorded a new digest, the `?v=` cache-bust moved, and `check_hosted.py` would
have reported drift -- every one of them saying *the data changed* when it had
not. **A digest that moves on its own is worse than no digest, because it is
believed.**

The sabotage core asked for is `test_two_exports_with_no_change_agree`: build
the bundle twice over identical inputs and require the bytes to match. Without
it this file passes just as well against the old `gzip.compress` call, because
every other property it checks was already true.
"""

import hashlib
import importlib.util
import os
import shutil
import sys
import time

REPO = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, REPO)

_p = os.path.join(REPO, "corpora", "export_teaser_data.py")
_s = importlib.util.spec_from_file_location("etd_inline_test", _p)
etd = importlib.util.module_from_spec(_s)
_s.loader.exec_module(etd)


def _stage(tmp_path):
    """A directory holding the four files `write_inline` bundles."""
    d = tmp_path / "data"
    d.mkdir()
    for i, name in enumerate(etd.OUT_FILES):
        (d / name).write_bytes(b'{"n":%d,"pad":"%s"}' % (i, b"x" * 400))
    return str(d)


# ------------------------------------------------------------ the sabotage
def test_two_exports_with_no_change_agree(tmp_path):
    """Bundle twice over identical bytes; the results must be identical.

    A second apart, deliberately -- the defect was a timestamp, so a test that
    ran both in the same clock tick could pass against the broken version.
    """
    out = _stage(tmp_path)
    etd.write_inline(out)
    first = hashlib.sha256(
        open(os.path.join(out, etd.INLINE_FILE), "rb").read()).hexdigest()

    time.sleep(1.1)

    etd.write_inline(out)
    second = hashlib.sha256(
        open(os.path.join(out, etd.INLINE_FILE), "rb").read()).hexdigest()

    assert first == second, (
        "inline.js changed with no change to the data: %s then %s. A digest "
        "that moves on its own reports drift that did not happen."
        % (first[:16], second[:16]))


def test_the_gzip_header_carries_no_timestamp():
    """Named directly, so the cause is asserted and not only its symptom.

    Bytes 4-7 of a gzip member are MTIME, little-endian. The sabotage above
    would also pass if someone froze the clock; this says what is actually
    required.
    """
    blob = etd._stable_gzip(b"whatever")
    assert blob[:2] == b"\x1f\x8b", "not a gzip member"
    assert blob[4:8] == b"\x00\x00\x00\x00", (
        "the gzip header carries a timestamp: %r" % (blob[4:8],))


def test_a_real_change_still_moves_the_digest(tmp_path):
    """The mirror. Without it, `_stable_gzip` returning a constant passes."""
    out = _stage(tmp_path)
    etd.write_inline(out)
    before = hashlib.sha256(
        open(os.path.join(out, etd.INLINE_FILE), "rb").read()).hexdigest()

    first = os.path.join(out, etd.OUT_FILES[0])
    shutil.copyfile(first, first + ".bak")
    open(first, "wb").write(b'{"n":0,"changed":true}')
    etd.write_inline(out)
    after = hashlib.sha256(
        open(os.path.join(out, etd.INLINE_FILE), "rb").read()).hexdigest()

    assert before != after, (
        "inline.js did not move when a bundled file changed, which is the "
        "failure the determinism fix must not introduce")


def test_the_bundle_still_round_trips(tmp_path):
    """Determinism is worthless if the bytes stop decompressing."""
    import base64
    import gzip
    import json
    import re
    out = _stage(tmp_path)
    etd.write_inline(out)
    text = open(os.path.join(out, etd.INLINE_FILE), encoding="utf-8").read()
    body = re.search(r"window\.__ONEGROUND_TEASER__ = (\{.*)", text,
                     re.S).group(1).rstrip().rstrip(";")
    doc = json.loads(body)
    for name, entry in doc["files"].items():
        raw = gzip.decompress(base64.b64decode(entry["gzip_b64"]))
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"], name
        assert len(raw) == entry["bytes"], name
