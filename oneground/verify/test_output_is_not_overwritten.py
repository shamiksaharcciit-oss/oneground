"""A verify run does not write over another run's receipts (task 044j).

**This is the guard whose absence cost two weeks.** On 2026-09-13 a pod run
wrote `verify.json` into a workdir that already held the 9 September run's
receipts. Nothing refused, nothing kept a copy, and the evidence behind a
verdict the public site was publishing stopped existing -- while the site went
on publishing it for thirteen days, because the export that would have
replaced it was separately broken.

Core asked for the sabotage first and it is `test_the_sabotage`: run twice
into the same target without the flag, require the second to refuse, and
require the first run's digest to be unchanged afterwards. The second half is
the one that matters -- a refusal that fires *after* clobbering the file would
pass a test that only checked for the exception.
"""

import hashlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground import verify as V                              # noqa: E402


def _place(wd, env_id, marker="first"):
    os.makedirs(wd, exist_ok=True)
    with open(os.path.join(wd, "verify.json"), "w", encoding="utf-8") as f:
        json.dump({"environment_id": env_id, "marker": marker}, f)
    with open(os.path.join(wd, "verify_info.json"), "w", encoding="utf-8") as f:
        json.dump({"environment_id": env_id}, f)
    return _digest(os.path.join(wd, "verify.json"))


def _digest(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


# ----------------------------------------------------------- the sabotage
def test_the_sabotage(tmp_path):
    """Two runs, two environments, one directory. The second must refuse and
    the first must survive it byte for byte."""
    wd = str(tmp_path / "run")
    before = _place(wd, "tf8sd2usxbblsm")

    with pytest.raises(V.VerifyOutputExists) as e:
        V.guard_verify_output(wd, "1ombs4scr257a5", log_fn=lambda m: None)

    msg = str(e.value)
    assert "tf8sd2usxbblsm" in msg and "1ombs4scr257a5" in msg, msg
    assert _digest(os.path.join(wd, "verify.json")) == before, (
        "the refusal fired but the file had already been written over")
    assert json.load(open(os.path.join(wd, "verify.json"),
                          encoding="utf-8"))["marker"] == "first"


def test_the_real_pair_of_environment_ids(tmp_path):
    """NOT synthetic in its ids: these are the two runs that collided.

    9 September's receipts were destroyed by 13 September's run. With this
    guard in place that write refuses.
    """
    wd = str(tmp_path / "arxiv-150k-via-characterize")
    _place(wd, "tf8sd2usxbblsm")
    with pytest.raises(V.VerifyOutputExists):
        V.guard_verify_output(wd, "1ombs4scr257a5", log_fn=lambda m: None)


# --------------------------------------------------- what it does allow
def test_a_first_run_writes_freely(tmp_path):
    wd = str(tmp_path / "run")
    os.makedirs(wd)
    assert V.guard_verify_output(wd, "env-1", log_fn=lambda m: None) is None


def test_a_retry_of_the_same_environment_is_allowed_and_still_archived(tmp_path):
    """Archiving happens even when nothing is refused.

    A retry of the same environment is legitimate, and its predecessor is
    still evidence. Archiving unconditionally is what makes the refusal cheap
    enough to keep -- a guard that turns every honest re-run into an argument
    with a flag is a guard someone disables.
    """
    wd = str(tmp_path / "run")
    _place(wd, "env-1", marker="older")
    kept = V.guard_verify_output(wd, "env-1", log_fn=lambda m: None)
    assert kept, "the previous pair was not archived"
    archived = os.path.join(wd, V.DISPLACED_VERIFY_DIR, "env-1", "verify.json")
    assert os.path.exists(archived)
    assert json.load(open(archived, encoding="utf-8"))["marker"] == "older"


def test_replace_archives_before_it_allows(tmp_path):
    """The flag permits the write and does not permit the loss."""
    wd = str(tmp_path / "run")
    _place(wd, "tf8sd2usxbblsm", marker="the nine september run")
    kept = V.guard_verify_output(wd, "1ombs4scr257a5", replace=True,
                                 log_fn=lambda m: None)
    archived = os.path.join(wd, V.DISPLACED_VERIFY_DIR,
                            "tf8sd2usxbblsm", "verify.json")
    assert os.path.exists(archived), kept
    got = json.load(open(archived, encoding="utf-8"))
    assert got["marker"] == "the nine september run"
    assert got["environment_id"] == "tf8sd2usxbblsm"


def test_the_archive_is_not_itself_overwritten(tmp_path):
    """The same defect one directory down is how it would come back.

    Two displacements of the same environment must not collapse into one
    archived file.
    """
    wd = str(tmp_path / "run")
    _place(wd, "env-1", marker="a")
    V.guard_verify_output(wd, "env-1", log_fn=lambda m: None)
    _place(wd, "env-1", marker="b")
    V.guard_verify_output(wd, "env-1", log_fn=lambda m: None)
    d = os.path.join(wd, V.DISPLACED_VERIFY_DIR, "env-1")
    kept = sorted(n for n in os.listdir(d) if n.startswith("verify."))
    assert len(kept) >= 2, kept
    markers = sorted(json.load(open(os.path.join(d, n), encoding="utf-8"))
                     .get("marker") for n in kept
                     if n.startswith("verify.") and "info" not in n)
    assert markers == ["a", "b"], markers


def test_an_unreadable_existing_file_still_refuses(tmp_path):
    """A corrupt verify.json is not a licence to overwrite it.

    Its environment cannot be read, so it cannot be shown to be the same run
    -- and 'I could not tell' is the case where destroying evidence is least
    excusable.
    """
    wd = str(tmp_path / "run")
    os.makedirs(wd)
    open(os.path.join(wd, "verify.json"), "w").write("{ not json")
    with pytest.raises(V.VerifyOutputExists) as e:
        V.guard_verify_output(wd, "env-1", log_fn=lambda m: None)
    assert "unreadable" in str(e.value)


def test_the_refusal_names_the_remedy(tmp_path):
    wd = str(tmp_path / "run")
    _place(wd, "env-old")
    with pytest.raises(V.VerifyOutputExists) as e:
        V.guard_verify_output(wd, "env-new", log_fn=lambda m: None)
    msg = str(e.value)
    assert "replace_verify" in msg
    assert "untouched" in msg
