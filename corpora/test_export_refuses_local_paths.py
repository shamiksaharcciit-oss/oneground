"""The exporter refuses to publish a local path (task 044e, core's request).

`write_json` is the one writer in this project that bypasses
`receipts.write_json_stable`, and the file it writes is the only one that is
actually published. So task 044g's runtime refusal arrives here too, at the
publishing boundary.

**The sabotage is the point.** A refusal nobody has watched refuse is a
refusal nobody has tested: `test_the_sabotage_is_refused` plants a real local
path in a payload shaped like the real one and requires the write to fail and
the file not to exist. Without it, this file passes just as well against a
`refuse_local_paths` whose body is `return`.
"""

import importlib.util
import json
import os
import sys

import pytest

REPO = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, REPO)

_p = os.path.join(REPO, "corpora", "export_teaser_data.py")
_s = importlib.util.spec_from_file_location("etd_under_test", _p)
etd = importlib.util.module_from_spec(_s)
_s.loader.exec_module(etd)


# ------------------------------------------------------- the sabotage
@pytest.mark.parametrize("planted", [
    r"C:\Users\user\projects\oneground\runs\x\verify.json",
    "C:/Users/user/projects/oneground/runs/x/verify.json",
    "/home/user/oneground/runs/x/verify.json",
    "/Users/user/oneground/runs/x/verify.json",
    "/workspace/oneground/requirements.pod.yaml",
    "~/oneground/runs/x/verify.json",
    r"~\oneground\runs\x\verify.json",
    r"\\fileserver\share\oneground\verify.json",
])
def test_the_sabotage_is_refused(tmp_path, planted):
    """Plant one, watch it refuse, and confirm nothing was written.

    The payload is shaped like the real one -- the offending string is buried
    three levels down beside honest data -- because a refusal that only
    inspects the top level would pass a flat test and publish the real file.
    """
    out = tmp_path / "values.json"
    payload = {
        "schema": 1,
        "measured": {"boundary_crispness": 0.036},
        "verdict": {"calibration": {"engine_line": {"source": planted}}},
    }
    with pytest.raises(SystemExit) as e:
        etd.write_json(str(out), payload)
    assert "refusing to write" in str(e.value)
    assert "verdict.calibration.engine_line.source" in str(e.value), e.value
    assert not out.exists(), "the file was written despite the refusal"


def test_the_refusal_names_the_key_and_does_not_repair(tmp_path):
    """Named, because a refusal that says only 'something is wrong' makes the
    reader search; and not repaired, because a page datum quietly corrected on
    the way out leaves the exporter wrong and tells nobody."""
    out = tmp_path / "values.json"
    payload = {"a": {"b": {"path": "/home/user/x.yaml"}}}
    with pytest.raises(SystemExit) as e:
        etd.write_json(str(out), payload)
    msg = str(e.value)
    assert "a.b.path" in msg
    assert "/home/user/x.yaml" in msg
    assert "public_path" in msg
    assert "Not repaired on purpose" in msg


# ------------------------------------------------- it is not indiscriminate
@pytest.mark.parametrize("honest", [
    "runs/arxiv-smoke/verify.json",
    "fixtures/arxiv-150k/ground_view_base.parquet",
    "tasks/044c-centroid-count.sweep/arxiv-150k.default.json",
    "oneground/cost/prices.example.yaml",
    "https://oneproof.dev/oneground/lab",
    "a second centroid inside 1.20x of the first",
    "recall@10 at one-region routing",
])
def test_an_honest_value_is_written(tmp_path, honest):
    """A refusal that fires on correct values gets switched off.

    Repo-relative paths are the correct form, and receipts and page data are
    full of prose and URLs with slashes in them.
    """
    out = tmp_path / "values.json"
    etd.write_json(str(out), {"v": honest})
    assert json.loads(out.read_text(encoding="utf-8"))["v"] == honest


def test_a_real_payload_passes(tmp_path):
    """The k_sweep block as the export actually builds it, through the writer
    that now refuses. If the thing this task adds cannot be published, the
    refusal is wrong rather than the block."""
    out = tmp_path / "values.json"
    etd.write_json(str(out), {"measured": {"k_sweep": etd.k_sweep_block()}})
    got = json.loads(out.read_text(encoding="utf-8"))
    assert got["measured"]["k_sweep"]["source"].startswith("tasks/")
    assert len(got["measured"]["k_sweep"]["rows"]) == 9


# --------------------------------------------------- the check is not vacuous
def test_the_matcher_would_catch_what_is_live_today():
    """NOT synthetic. The string that is in the published values.json right
    now -- a path that was recorded, travelled into published data, and was
    redacted by hand. This refusal is what makes the hand unnecessary."""
    live = (r"C:\Users\<developer>\projects\oneground-012\runs"
            r"\arxiv-smoke\verify.json")
    assert list(etd.local_paths_in({"source": live})), (
        "the matcher does not catch the one instance already in the "
        "published data")
