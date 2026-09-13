"""Every command driven through `cli.main`, not through its module.

**Synthetic corpora throughout.** These assert wiring, not numbers: that each
subcommand's handler can actually call the function behind it with the
arguments it passes.

WHY THIS FILE EXISTS
--------------------
Three times in three tasks, a handler was changed to pass an argument the
function behind it does not take, and a full green suite said nothing:

    build_manifest(...)          013b   NameError, found by running a report
    characterize.run(env_stamp=) 013b   TypeError, found by a wheel install
    report.run(env_stamp=)       013b   caught only because the first one was

Every existing test calls `characterize.run(...)` or `report.run(...)`
directly. Nothing called `cli.main(["characterize", ...])`, so the seam
between the parser, the guard decorator and the function was never crossed by
a test -- and that seam is exactly where all three broke.

These are deliberately shallow: each command is driven far enough to prove the
call connects, and no further. A test that also checked the numbers would be
slow enough that someone would eventually stop running it, and the numbers are
covered elsewhere.
"""

import io
import json
import os
import sys
import tempfile

import numpy as np
import yaml

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from oneground import cli                              # noqa: E402


def _corpus(tmp, n=300, dim=16, n_q=60):
    rng = np.random.default_rng(3)
    x = rng.normal(size=(n, dim)).astype(np.float32)
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    q = x[rng.choice(n, size=n_q, replace=False)].copy()
    np.save(os.path.join(tmp, "vectors.npy"), x)
    np.save(os.path.join(tmp, "queries.npy"), q)
    return os.path.join(tmp, "vectors.npy"), os.path.join(tmp, "queries.npy")


def _requirements(tmp, tier1=True):
    vec, q = _corpus(tmp) if tier1 else (None, None)
    data = {
        "oneground": 1,
        "run": {"name": "cli", "seed": 1, "mode": "measure",
                "workdir": os.path.join(tmp, "out")},
        "simulate": {"kind": "declared", "families": ["single_node_hnsw"],
                     "node_counts": [1], "ground_truth_k": 10},
        "constraints": {"kind": "declared",
                        "recall_at_k": {"k": 10, "min": 0.5},
                        "storage_amplification_max": 2.0},
    }
    if tier1:
        data["corpus"] = {"sample": {
            "kind": "receipt",
            "vectors": {"path": vec, "normalized": True},
            "queries": {"path": q, "count_min": 50},
            "target_sample_size": 300}}
    else:
        data["corpus"] = {"declared": {
            "kind": "declared", "size_now": 100000, "dimension": 16,
            "corpus_type": "papers", "text_length": "medium",
            "topics_trend": True, "time_ordered": True,
            "nearest_fixture": "none"}}
    p = os.path.join(tmp, "requirements.yaml")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump(data, f, sort_keys=False)
    return p


def _main(argv):
    """Run `cli.main`, capturing stdout. Returns (exit code, output)."""
    buf, orig = io.StringIO(), sys.stdout
    sys.stdout = buf
    try:
        code = cli.main(argv)
    except SystemExit as e:                     # argparse's own exits
        code = e.code
    finally:
        sys.stdout = orig
    return code, buf.getvalue()


# ------------------------------------------------------------- the seams
def test_characterize_runs_through_the_cli_synthetic():
    """The call that has been raising TypeError since task 013b."""
    with tempfile.TemporaryDirectory() as tmp:
        code, out = _main(["characterize", _requirements(tmp)])
        assert code == 0, out
        wd = os.path.join(tmp, "out")
        assert os.path.exists(os.path.join(wd, "characterization.json")), out


def test_characterize_stamps_the_environment_it_ran_in_synthetic():
    """The reason the parameter exists at all."""
    with tempfile.TemporaryDirectory() as tmp:
        code, out = _main(["characterize", _requirements(tmp)])
        assert code == 0, out
        with open(os.path.join(tmp, "out", "build_info.json"),
                  encoding="utf-8") as f:
            bi = json.load(f)
        assert "environment" in bi, sorted(bi)
        assert bi["environment"]["environment_id"], bi["environment"]
        assert "pinned" in bi["environment"]
        assert "executable" not in bi["environment"], bi["environment"]


def test_a_declared_corpus_runs_through_the_cli_synthetic():
    """Tier 2's handler passes the stamp through a different function."""
    with tempfile.TemporaryDirectory() as tmp:
        code, out = _main(["characterize", _requirements(tmp, tier1=False)])
        assert code == 0, out
        with open(os.path.join(tmp, "out", "build_info.json"),
                  encoding="utf-8") as f:
            bi = json.load(f)
        assert bi["tier"] == 2
        assert "environment" in bi, sorted(bi)


def test_simulate_and_report_run_through_the_cli_synthetic():
    """The whole Tier-1 chain through the parser, in one go."""
    with tempfile.TemporaryDirectory() as tmp:
        req = _requirements(tmp)
        assert _main(["characterize", req])[0] == 0
        code, out = _main(["simulate", req])
        assert code == 0, out
        code, out = _main(["report", req])
        assert code == 0, out
        wd = os.path.join(tmp, "out")
        for name in ("simulate.json", "report.json", "manifest.yaml"):
            assert os.path.exists(os.path.join(wd, name)), (name, out)


def test_the_report_stamps_the_environment_through_the_cli_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        req = _requirements(tmp)
        _main(["characterize", req])
        _main(["simulate", req])
        assert _main(["report", req])[0] == 0
        with open(os.path.join(tmp, "out", "report.json"),
                  encoding="utf-8") as f:
            report = json.load(f)
        assert "run_environment" in report, sorted(report)


def test_version_prints_both_strings():
    """PEP 440 for the resolver, the display name for the reader.

    Task 018: the two coincide at `0.1.0`, so `x in out` for both would pass
    on a line that printed only one of them -- the assertion would be green
    and testing nothing. The shape is checked instead: both when they differ,
    one when they do not.
    """
    from oneground import __display_version__, __version__
    code, out = _main(["--version"])
    assert __display_version__ in out, out
    assert __version__ in out, out
    if __display_version__ == __version__:
        assert out.strip() == "oneground %s" % __version__, out
    else:
        assert out.strip() == "oneground %s (%s)" % (__display_version__,
                                                     __version__), out


def test_an_unknown_command_does_not_crash():
    code, _out = _main(["definitely-not-a-command"])
    assert code != 0


# ---------------------------------------------- every handler is callable
def test_every_top_level_handler_accepts_what_its_wiring_passes():
    """The class of defect this file exists for, checked directly.

    A handler decorated with `@guarded` is called as `f(args, rest,
    env_stamp=...)` when it declares the keyword. If it declares it and the
    function behind it does not, the failure is a TypeError at run time --
    which is what shipped. Here the signatures are compared before anything
    runs.
    """
    import inspect

    from oneground import characterize, report

    # Each pair: the module function a handler calls, and the keyword it is
    # called with. Extend when a handler starts passing something new.
    pairs = [
        (characterize.run, "env_stamp"),
        (characterize.run_declared, "env_stamp"),
        (report.run, "env_stamp"),
        (report.run_declared, "env_stamp"),
        (report.build_manifest, "env_stamp"),
    ]
    for fn, keyword in pairs:
        params = inspect.signature(fn).parameters
        assert keyword in params, (
            f"{fn.__module__}.{fn.__qualname__} does not accept {keyword!r}, "
            "but something passes it")


def _run_all():
    tests = [(n, o) for n, o in sorted(globals().items())
             if n.startswith("test_") and callable(o)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"ok    {name}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed} passed, {failed} failed "
          f"(of {len(tests)} collected)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())
