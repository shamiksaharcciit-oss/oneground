"""A refusal is produced where it is raised, once (task 046).

`tasks/finding-refusals-arrive-as-tracebacks.md` measured the defect: the
project's own refusal type escaped `cli.main` as a traceback, so the
commonest refusal in the product was met as a crash by every command-line
user. These tests are the fix, and the fence around the classification the
supervisor reads.
"""

import os
import subprocess
import sys

import pytest

from oneground import jobs, refusals

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(*args):
    """A real process, because the defect was in what a process returns."""
    code = (f"import sys; sys.path.insert(0, {REPO!r});"
            " from oneground.cli import main; sys.exit(main())")
    r = subprocess.run([sys.executable, "-c", code, *args],
                       capture_output=True, text=True, timeout=300, cwd=REPO)
    return r.returncode, (r.stdout + r.stderr)


# --------------------------------------------- the defect, and the fix
def test_a_missing_requirements_file_is_a_refusal_not_a_traceback():
    """The measured case. It exited 1 with a stack trace and the carefully
    written sentence on the last line; it now exits 2 with the sentence and
    nothing else."""
    code, out = _run("characterize", "nope.yaml")
    assert code == refusals.REFUSED_EXIT == 2, out
    assert "Traceback (most recent call last)" not in out
    assert "requirements file not found: nope.yaml" in out
    assert "oneground characterize: refused." in out


def test_the_refusal_is_one_line():
    """Verbatim and unadorned. `docs/INTERFACE.md` §4.4 has the UI show this
    string, so anything wrapped around it is something the UI would show."""
    _code, out = _run("characterize", "nope.yaml")
    lines = [ln for ln in out.splitlines() if "refused." in ln]
    assert len(lines) == 1, out
    assert lines[0].endswith("requirements file not found: nope.yaml")


def test_a_directory_is_a_refusal_not_a_permission_error():
    """The measured case from `tasks/finding-a-path-check-that-accepts-a-
    directory.md`: `oneground characterize .` used to reach `open()` and
    raise IsADirectoryError/PermissionError -- neither a declared refusal,
    so it escaped as a traceback, and the Windows message is actively
    misleading about what is wrong."""
    code, out = _run("characterize", ".")
    assert code == refusals.REFUSED_EXIT == 2, out
    assert "Traceback (most recent call last)" not in out
    assert "PermissionError" not in out and "IsADirectoryError" not in out
    assert ". is a directory, not a requirements file" in out


def test_a_genuine_failure_keeps_its_traceback():
    """The half that makes the fix safe. A crash presented as a refusal
    would tell the user the tool meant it, which is worse than a traceback.
    """
    code = (f"import sys; sys.path.insert(0, {REPO!r});"
            " from oneground import cli;"
            " cli._dispatch = lambda argv: (_ for _ in ()).throw("
            "RuntimeError('a real bug')); sys.exit(cli.main(['simulate']))")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                       text=True, timeout=300, cwd=REPO)
    assert r.returncode == 1
    assert "Traceback (most recent call last)" in r.stderr
    assert "RuntimeError: a real bug" in r.stderr
    assert "refused" not in r.stderr


# ---------------------------------------------------- the declaration
def test_every_declared_refusal_carries_a_reason():
    for name, why in refusals.REFUSALS.items():
        assert name.startswith("oneground."), name
        assert why and len(why) > 25, name


def test_the_exclusions_are_named_with_their_reason():
    """An exception wrongly called a refusal would hide a defect. The ones
    left out say why, so the next reader does not have to re-decide."""
    for name, why in refusals.NOT_REFUSALS.items():
        assert why and len(why) > 25, name
    assert not set(refusals.REFUSALS) & set(refusals.NOT_REFUSALS)


def test_the_two_types_that_carried_both_outcomes_are_split():
    """They used to be one class each, promising a refusal and a failure at
    once, and a caller handed one could not tell which it got.

    `EmbedError` said so in its docstring and was raised nowhere, which made
    the split free. `ModelUnresolved` was live in three places and said so
    too: *a typo and no network need different actions from the reader*. The
    distinction was in the message, where a person can act on it and no
    caller can; it is in the type now.
    """
    from oneground import embed
    from oneground.embed import registry

    # each base is kept, so `except Base` still catches both halves
    assert issubclass(embed.NoModelNamed, embed.EmbedError)
    assert issubclass(embed.EmbedFailed, embed.EmbedError)
    assert issubclass(registry.ModelUnknown, registry.ModelUnresolved)
    assert issubclass(registry.ModelUnusable, registry.ModelUnresolved)

    # and the halves land on opposite sides of the table
    assert refusals.is_refusal(embed.NoModelNamed("x"))
    assert not refusals.is_refusal(embed.EmbedFailed("x"))
    assert refusals.is_refusal(registry.ModelUnknown("x"))
    assert not refusals.is_refusal(registry.ModelUnusable("x"))

    # the base of each stays out: a caller catching it said it does not care
    assert not refusals.is_refusal(embed.EmbedError("x"))
    assert not refusals.is_refusal(registry.ModelUnresolved("x"))


def test_the_undecidable_site_still_raises_the_base():
    """One of the three sites cannot tell a typo from an unreachable hub --
    sentence-transformers raises much the same thing for both. Guessing there
    is the failure the split exists to prevent, so it keeps the base, and
    the base is excluded.

    Asserted on the source, because the site cannot be reached without a
    network and a model download.
    """
    import ast
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(refusals.__file__)),
                        "embed", "registry.py")
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), path)
    raised = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) \
                and isinstance(node.exc.func, ast.Name):
            raised.append(node.exc.func.id)
    assert raised.count("ModelUnresolved") == 1, raised
    assert "ModelUnknown" in raised and "ModelUnusable" in raised


def test_the_exclusion_asymmetry_is_recorded_where_the_decision_is_made():
    """Which way to lean when a guess is unavoidable. Calling a failure a
    refusal tells the user the tool meant it; calling a refusal a failure
    says less rather than something false."""
    import inspect
    src = inspect.getsource(refusals)
    assert "the tool MEANT it" in src
    assert "saying LESS rather than saying" in src
    assert 'never "known to be a failure"' in src


def test_a_declared_type_actually_exists_and_is_an_exception():
    """A name in the table that no longer resolves would silently stop
    matching, and every refusal of that kind would go back to being a
    traceback with nothing to report it."""
    import importlib
    for name in list(refusals.REFUSALS) + list(refusals.NOT_REFUSALS):
        module, _, cls = name.rpartition(".")
        mod = importlib.import_module(module)
        obj = getattr(mod, cls, None)
        assert obj is not None, f"{name} does not resolve"
        assert isinstance(obj, type) and issubclass(obj, BaseException), name


def test_matching_is_exact_on_the_type():
    from oneground.intake import RequirementsError

    class Subclass(RequirementsError):
        pass

    assert refusals.is_refusal(RequirementsError("x"))
    assert not refusals.is_refusal(Subclass("x")), (
        "a subclass inherits the class, not the reason in the table")
    assert not refusals.is_refusal(ValueError("x"))


# ------------------------------------- the exit-code mapping, as data
def test_the_mapping_declares_a_reason_for_every_code():
    for code, (state, why) in jobs.EXIT_MEANING.items():
        assert why and len(why) > 20, code
        assert state in ("done", "refused", "failed"), code


def test_exit_zero_is_done_and_exit_two_is_refused():
    assert jobs.classify("simulate", 0)[0] == "done"
    assert jobs.classify("simulate", 2)[0] == "refused"


# Task 046 contract changes 5 and 6 repaired the two stages that made this
# row mean two things. With EXIT_CONTRACT empty, every stage's exit 1 means
# the same thing, and classify no longer needs a workdir to decide it.
@pytest.mark.parametrize("stage", jobs.STAGES)
def test_exit_one_is_failed_for_every_stage(stage):
    state, why = jobs.classify(stage, 1)
    assert state == "failed", why
    assert "did not finish" in why


def test_an_unexpected_code_is_failed_and_says_it_was_unexpected():
    state, why = jobs.classify("simulate", 137)
    assert state == "failed"
    assert "137" in why and "deliberately" in why


def test_the_exit_contract_now_has_no_exceptions():
    """Both declared exceptions -- `("simulate", 1)` and `("pod plan", 1)`
    -- were the repair `tasks/046-contract-changes.report.md` items 5 and 6
    deferred. `_cmd_simulate` now returns 0 with the drop named in
    simulate_info.json, and `cmd_plan` returns `refusals.REFUSED_EXIT` for
    both of its refusals. An empty EXIT_CONTRACT means the rule -- a stage's
    exit code says whether it ran, never what it found -- holds without
    exception."""
    assert jobs.EXIT_CONTRACT == {}
