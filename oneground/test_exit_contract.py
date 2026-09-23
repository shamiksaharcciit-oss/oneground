"""A stage's exit code says whether the command ran, never what it found.

Task 046. The assertion that makes `jobs.EXIT_CONTRACT`'s rule enforceable
rather than documented — and it is the test that did not exist when the rule
was worked out, which is why the rule was worth working out.

It is a source check, and deliberately so. Running six stages to see what
they return would need a corpus, an engine and an hour; parsing what they
*can* return needs neither and covers every branch rather than the ones a
fixture happens to reach.
"""

import ast
import os

import pytest

from oneground import jobs, refusals

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(REPO, "oneground", "cli.py")

#: The handler each stage's command dispatches to.
HANDLERS = {
    "characterize": "_cmd_characterize", "simulate": "_cmd_simulate",
    "verify": "_cmd_verify", "report": "_cmd_report",
    "chunk": "_cmd_chunk", "propose": "_cmd_propose",
}


def _handlers():
    with open(CLI, encoding="utf-8") as f:
        tree = ast.parse(f.read(), CLI)
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            found[node.name] = node
    return found


def _literal_returns(fn):
    """`[(lineno, value)]` for every `return <int literal>` in a function,
    excluding nested functions, which are somebody else's contract."""
    out = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, int):
            out.append((node.lineno, node.value.value))
    return out


def test_every_stage_handler_exists():
    """If a handler is renamed this test must fail rather than silently
    checking nothing -- an empty set of things to check is the most common
    way a source scan stops meaning anything."""
    found = _handlers()
    for stage, name in HANDLERS.items():
        assert name in found, f"{stage}: no handler {name} in cli.py"


@pytest.mark.parametrize("stage", sorted(HANDLERS))
def test_a_stage_returns_zero_or_a_declared_non_zero(stage):
    """**The rule, enforced.** A stage that returns non-zero is saying it did
    not run or declined. Anything else is a finding travelling in the exit
    code, where `classify` will read it as `refused` or `failed` and the page
    will say *the tool declined* about an answer the tool gave.

    A permitted non-zero is one listed in `jobs.EXIT_CONTRACT` with a reason.
    Adding one costs a sentence, which is the point: the sentence is where
    you notice you are about to report a result through a process.
    """
    fn = _handlers()[HANDLERS[stage]]
    for lineno, value in _literal_returns(fn):
        if value == 0:
            continue
        if value == refusals.REFUSED_EXIT:
            # The rule's own second line. A refusal is a permitted non-zero
            # everywhere, so it needs no per-stage exception -- `propose`
            # returns it for `ProposeError`, in its own words, "a refusal is
            # not a crash".
            #
            # The first version of this test demanded a declaration for it
            # and failed on `propose`, which is the check being adjacent to
            # the question one more time: it asked "is this non-zero
            # declared" where the rule says "is this non-zero a fate".
            continue
        key = (stage, value)
        assert key in jobs.EXIT_CONTRACT, (
            f"cli.py:{lineno}: {stage} returns {value}, which is not 0 and "
            f"not declared in jobs.EXIT_CONTRACT. A stage's exit code says "
            f"whether the command ran, never what it found -- if this is a "
            f"finding, it belongs in the artifact; if it is a fate, declare "
            f"it with the reason.")


def test_every_declared_exception_carries_a_reason_and_is_real():
    """A declaration nobody can read is a permission nobody audits, and an
    entry for a return that no longer exists is a permission that outlived
    its case."""
    handlers = _handlers()
    for (stage, code), why in jobs.EXIT_CONTRACT.items():
        assert stage in HANDLERS, stage
        assert code != 0, (stage, code)
        assert why and len(why) > 25, (stage, code)
        values = [v for _l, v in _literal_returns(handlers[HANDLERS[stage]])]
        assert code in values, (
            f"{stage} no longer returns {code}; the exception outlived the "
            "case it was written for and should go")


def test_the_one_declared_exception_is_the_one_that_costs_the_classifier():
    """Pinned so the connection is not lost: `simulate` returning 1 for
    dropped configurations is the sole reason `EXIT_MEANING[1]` means two
    things and `classify` has to consult the workdir at all.

    If this entry goes, that row collapses to *did not finish* and the
    workdir check becomes unnecessary. Stated here because the cost of a
    declared exception is easiest to see from the thing paying it.
    """
    assert set(jobs.EXIT_CONTRACT) == {("simulate", 1)}
    state, _why = jobs.EXIT_MEANING[1]
    assert state is None, (
        "exit 1 is undecided precisely because simulate uses it for a "
        "finding; if that changed, this row should have too")


def test_verify_returns_zero_when_an_engine_contradicts_the_simulation():
    """The rule already holding, which is why it was worth writing down.

    A contradiction is the sharpest possible negative result -- the tool ran,
    and the answer was that the simulation was wrong -- and `_cmd_verify`
    returns 0, because the contradiction goes into `verify.json`. The three
    outcomes live in the artifact, not in the process, holding at the process
    boundary without anyone having stated it there.
    """
    fn = _handlers()["_cmd_verify"]
    values = {v for _l, v in _literal_returns(fn)}
    assert values == {0}, (
        f"_cmd_verify returns {sorted(values)}; a contradiction is a result "
        "and belongs in verify.json, not in the exit code")
