"""The replay rule, and the fence around its exemptions.

`docs/INTERFACE.md` §2 names what must be byte-identical and what may differ.
This is the test that keeps the second list from growing quietly, because
that is what will be attempted the first time a replay differs for a reason
that looks legitimate.
"""

import json
import os

import pytest

from oneground import replay


def _workdir(root, name, *, run_at="2026-01-01T00:00:00Z", seconds=1.0,
             recall=0.932, dirty=False, commit="a" * 40, extra=None):
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    info = {
        "kind": "simulate", "run_at": run_at, "elapsed_seconds": seconds,
        "timings": {"build": seconds / 2},
        "platform": "Linux-6.8.0", "python_version": "3.12.3",
        "oneground": {"version": "0.1.0", "commit": commit, "dirty": dirty,
                      "source": "checkout", "note": ""},
        "invocation": {"command": ["simulate", "runs/x"], "note": ""},
    }
    if extra:
        info.update(extra)
    with open(os.path.join(d, "simulate_info.json"), "w",
              encoding="utf-8") as f:
        json.dump(info, f, sort_keys=True)
    with open(os.path.join(d, "simulate.json"), "w", encoding="utf-8") as f:
        json.dump({"rows": [{"config": "hnsw", "recall": recall}]}, f,
                  sort_keys=True)
    import hashlib
    lines = []
    for n in ("simulate.json", "simulate_info.json"):
        h = hashlib.sha256()
        with open(os.path.join(d, n), "rb") as f:
            h.update(f.read())
        lines.append("%s  %s" % (h.hexdigest(), n))
    with open(os.path.join(d, replay.MANIFEST), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return d


# --------------------------------------------------- the fence, first
def test_the_exemption_list_is_pinned_exactly():
    """Widening it means editing the declaration, this test, and writing a
    reason -- in one diff a reviewer sees whole.

    If this test fails because you added an entry: the question is not
    whether the field differs. It is whether a receipt that cannot reproduce
    it is recording the right thing. That is a finding, and the list stays
    where it is until it has been written up.
    """
    assert set(replay.MAY_DIFFER) == {
        "run_at", "elapsed_seconds", "timings",
        "oneground.dirty", "invocation.note",
    }


def test_every_exemption_carries_a_reason():
    for name, why in replay.MAY_DIFFER.items():
        assert why and len(why) > 30, name
        assert not why.endswith("."), name


def test_the_commit_is_not_exempt_although_dirty_beside_it_is():
    """The distinction the whole list turns on. `oneground.dirty` can flip
    without the code changing; `oneground.commit` is the field that says what
    ran, and a replay under a different commit is a different run."""
    assert replay._exempt("oneground.dirty")
    assert not replay._exempt("oneground.commit")
    assert not replay._exempt("invocation.command")
    assert replay._exempt("invocation.note")


# --------------------------------------------------- what it reports
def test_two_runs_of_one_command_match_across_the_exempt_fields(tmp_path):
    a = _workdir(str(tmp_path), "a", run_at="2026-01-01T00:00:00Z",
                 seconds=1.0, dirty=False)
    b = _workdir(str(tmp_path), "b", run_at="2026-02-02T09:09:09Z",
                 seconds=7.5, dirty=True)
    got = replay.compare(a, b)
    assert got["matches"], got["differing"]
    # and it says what it set aside rather than hiding it
    fields = {e["field"] for e in got["exempt"]}
    assert {"run_at", "elapsed_seconds", "oneground.dirty"} <= fields
    assert got["compared"] == 3


@pytest.mark.parametrize("kw,expect", [
    (dict(recall=0.9331), "simulate.json"),
    (dict(commit="b" * 40), "simulate_info.json"),
])
def test_a_real_difference_is_reported(tmp_path, kw, expect):
    """The mutants. Each changes one thing that must match, and the
    comparison has to name it -- otherwise the green above is worth nothing.
    """
    a = _workdir(str(tmp_path), "a")
    b = _workdir(str(tmp_path), "b", **kw)
    got = replay.compare(a, b)
    assert not got["matches"], got
    assert expect in {d["file"] for d in got["differing"]}


def test_a_manifest_line_for_a_non_exempt_file_must_match(tmp_path):
    """The manifest is not skipped because it covers files that may differ.
    Only the lines for those files are set aside; every other line is held.
    """
    a = _workdir(str(tmp_path), "a")
    b = _workdir(str(tmp_path), "b")
    # corrupt only the manifest's entry for simulate.json, leaving the file
    lines = open(os.path.join(b, replay.MANIFEST), encoding="utf-8").read()
    lines = lines.replace(lines.split("  ")[0], "0" * 64, 1)
    with open(os.path.join(b, replay.MANIFEST), "w", encoding="utf-8") as f:
        f.write(lines)
    got = replay.compare(a, b)
    assert not got["matches"]
    assert any(d["file"] == replay.MANIFEST and d["field"] == "simulate.json"
               for d in got["differing"]), got["differing"]


def test_a_missing_or_extra_file_is_a_difference(tmp_path):
    a = _workdir(str(tmp_path), "a")
    b = _workdir(str(tmp_path), "b")
    with open(os.path.join(b, "surprise.json"), "w", encoding="utf-8") as f:
        f.write("{}")
    got = replay.compare(a, b)
    assert not got["matches"]
    assert got["only_in_second"] == ["surprise.json"]


def test_comparing_a_directory_that_is_not_there_refuses(tmp_path):
    a = _workdir(str(tmp_path), "a")
    with pytest.raises(replay.ReplayError):
        replay.compare(a, str(tmp_path / "nowhere"))
