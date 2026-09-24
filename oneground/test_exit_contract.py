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

#: The handler each stage's command dispatches to, and the file it is in.
#:
#: The pod verbs are stages too -- `jobs.STAGES` says so -- and their
#: handlers live in `oneground/pod/cli.py`. The first version of this test
#: read only `oneground/cli.py`, so it checked six of the ten stages while
#: reading as though it checked all of them. Warning 1, in the test written
#: to enforce the rule.
HANDLERS = {
    "characterize": ("oneground/cli.py", "_cmd_characterize"),
    "simulate": ("oneground/cli.py", "_cmd_simulate"),
    "verify": ("oneground/cli.py", "_cmd_verify"),
    "report": ("oneground/cli.py", "_cmd_report"),
    "chunk": ("oneground/cli.py", "_cmd_chunk"),
    "propose": ("oneground/cli.py", "_cmd_propose"),
    "pod plan": ("oneground/pod/cli.py", "cmd_plan"),
    "pod status": ("oneground/pod/cli.py", "cmd_status"),
    "pod watch": ("oneground/pod/cli.py", "cmd_watch"),
    "pod fetch": ("oneground/pod/cli.py", "cmd_fetch"),
}


def _handlers():
    found = {}
    for rel in sorted({where for where, _n in HANDLERS.values()}):
        path = os.path.join(REPO, rel)
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), path)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                found[(rel, node.name)] = node
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


def test_every_stage_has_a_handler_named_here():
    """Two things, because either alone is a scan that checks nothing.

    Every stage in `jobs.STAGES` must appear here -- otherwise a stage added
    later is simply not examined, and this file passes while covering less
    than it did. And every handler named here must exist -- otherwise a
    rename makes the scan read a set of zero functions and say nothing
    cheerfully.
    """
    assert set(HANDLERS) == set(jobs.STAGES), (
        "a stage is missing from this test, so it is not being checked: "
        + repr(set(jobs.STAGES) ^ set(HANDLERS)))
    found = _handlers()
    for stage, key in HANDLERS.items():
        assert key in found, f"{stage}: no handler {key[1]} in {key[0]}"


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
            f"{HANDLERS[stage][0]}:{lineno}: {stage} returns {value}, "
            f"which is not 0 and "
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


def test_the_declared_exceptions_are_gone_and_the_row_collapsed():
    """The repair the two entries deferred: `_cmd_simulate` returns 0 with
    the drop named in simulate_info.json, and `pod plan`'s cmd_plan returns
    `refusals.REFUSED_EXIT` for both of its refusals. `EXIT_CONTRACT` is
    empty and `EXIT_MEANING[1]` collapsed to *did not finish*, which is what
    paying for the two declared exceptions bought back.
    """
    assert jobs.EXIT_CONTRACT == {}
    state, _why = jobs.EXIT_MEANING[1]
    assert state == jobs.FAILED


def test_verify_returns_zero_when_an_engine_contradicts_the_simulation():
    """The rule already holding, which is why it was worth writing down.

    A contradiction is the sharpest possible negative result -- the tool ran,
    and the answer was that the simulation was wrong -- and `_cmd_verify`
    returns 0, because the contradiction goes into `verify.json`. The three
    outcomes live in the artifact, not in the process, holding at the process
    boundary without anyone having stated it there.
    """
    fn = _handlers()[("oneground/cli.py", "_cmd_verify")]
    values = {v for _l, v in _literal_returns(fn)}
    assert values == {0}, (
        f"_cmd_verify returns {sorted(values)}; a contradiction is a result "
        "and belongs in verify.json, not in the exit code")
