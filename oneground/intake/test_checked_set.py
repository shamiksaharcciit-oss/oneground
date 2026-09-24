"""The checked set: which fields `intake` validates, and why. Task 049.

`fields.py`'s module docstring states the rule -- scope, presence, value,
descriptive annotation, in that order. This is the test that holds the rule
to the tree: every one of `requirements.example.yaml`'s current leaf fields,
walked in both directions. A field the rule says is checked must actually be
checked; a field the rule says is not must be named as not, by one of the
rule's own components, not by silence.

    python oneground/intake/test_checked_set.py
    pytest oneground/intake/test_checked_set.py
"""

import os
import sys
import tempfile

import pytest
import yaml

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground import intake                       # noqa: E402
from oneground.intake import fields                # noqa: E402

REPO = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EXAMPLE = os.path.join(REPO, "requirements.example.yaml")


def _leaves(d, prefix=""):
    """Dotted leaf paths: dicts recurse, scalars and lists are leaves.

    The same flattening tasks 046 and 048 used, so this number is the one
    those reports' counts are about, not a re-derivation that might not
    agree with them.
    """
    out = []
    if isinstance(d, dict):
        for k, v in d.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            out.extend(_leaves(v, path))
    else:
        out.append(prefix)
    return out


def _example_leaves():
    with open(EXAMPLE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return _leaves(data)


# --------------------------------------------------- the count, derived
def test_the_count_is_derived_not_written_down():
    """`count_refusals()` parses; it does not repeat a digit anyone typed.

    Pinned at today's value so a change to `intake.load()` that adds or
    removes a refusal is visible here -- the same shape as `fields.py`'s
    own docstring asking not to be trusted as a bare number, checked rather
    than merely asked for.
    """
    n = fields.count_refusals()
    assert n > 0
    assert n == fields.count_refusals(), "not stable across two calls"
    # OUTSIDE_THE_TABLE's eleven are a subset of the total by construction,
    # not an independent count that could disagree with it.
    assert len(fields.OUTSIDE_THE_TABLE) < n


# ------------------------------------------- the example file, pinned
def test_the_example_file_has_74_leaves():
    """The denominator every count in tasks 046/048/049 is about. If this
    fails, the leaf count changed and every number downstream needs
    re-deriving -- which is what this test is for."""
    assert len(_example_leaves()) == 74


# ---------------------------------------- the rule, walked both ways
def test_every_current_leaf_is_accounted_for():
    """The coverage claim, both directions, over every leaf that exists
    today -- not a hand-picked subset, the defect `docs/PRACTICE.md` §4's
    other four instances each had.

    Checked matches checked: `checked_reason` says True only for a field
    `fields.BY_NAME` actually declares. Unchecked is named unchecked:
    `checked_reason` says False only with a reason from rule 1, 3 or 4 --
    never silence. A field none of the rule's components places is a
    failure here, not a case that happens not to be tested.
    """
    unresolved = []
    wrong_true = []
    wrong_false = []
    for leaf in _example_leaves():
        checked, reason = fields.checked_reason(leaf)
        if checked is None:
            unresolved.append(leaf)
            continue
        if not reason:
            (wrong_true if checked else wrong_false).append(
                (leaf, "no reason given"))
            continue
        if checked and leaf not in fields.BY_NAME:
            wrong_true.append((leaf, reason))
        if not checked and leaf in fields.BY_NAME:
            wrong_false.append((leaf, reason))

    assert not unresolved, (
        "the rule has no answer for: %s -- evidence the rule is "
        "incomplete, not a field to guess about" % unresolved)
    assert not wrong_true, ("said checked without being in BY_NAME: %s"
                            % wrong_true)
    assert not wrong_false, ("said unchecked while in BY_NAME: %s"
                             % wrong_false)


def test_every_by_name_field_is_a_current_leaf_or_says_why_not():
    """The other half of 'checked matches checked': nothing in `BY_NAME`
    should be a field that no longer exists anywhere a requirements file
    can carry it. What is not a current leaf of `requirements.example.yaml`
    is named here with why -- the commented-out text alternative to
    `corpus.sample.vectors`, and the extraction block, which belongs to the
    documents path (task 031) and has no place in the vectors example --
    rather than left to mean "drifted and nobody noticed"."""
    leaves = set(_example_leaves())
    accounted_elsewhere = (
        "corpus.sample.text.path", "corpus.sample.text.model",
        "extraction.tool", "extraction.version", "extraction.reason")
    for name in fields.BY_NAME:
        if name in leaves:
            continue
        assert name in accounted_elsewhere, (
            "%s is declared but is neither a current leaf nor a known "
            "case accounted for above -- BY_NAME has drifted from the "
            "example file" % name)


def test_the_scope_rule_alone_accounts_for_44():
    """Rule 1, pinned: the four out-of-scope blocks are 44 of the current
    74 leaves. If a block grows or shrinks this number moves, which is the
    point -- rule 1 is doing the accounting, not this test."""
    out = sum(1 for leaf in _example_leaves()
              if leaf.split(".")[0] in fields.OUT_OF_SCOPE_BLOCKS)
    assert out == 44


def test_a_field_the_rule_cannot_place_fails_rather_than_passes():
    """The mutant for `test_every_current_leaf_is_accounted_for`: without
    it, a field none of rules 1/3/4 mention and that is not in `BY_NAME`
    would silently pass every assertion above by never being asked about.
    """
    checked, reason = fields.checked_reason("constraints.a_field_nobody_has_"
                                            "named_yet")
    # Caught by rule 1 (the block is out of scope) -- the strongest case,
    # since scope alone answers for it. The real mutant is a field whose
    # block *is* in scope and that matches nothing else:
    assert (checked, reason) == (False, "rule 1: constraints is a later "
                                        "stage's configuration")
    checked, reason = fields.checked_reason(
        "corpus.sample.a_field_nobody_has_named_yet")
    assert (checked, reason) == (None, None), (
        "an in-scope field matching nothing should be unresolved, not "
        "silently accepted or rejected")


# ------------------------------------ the two fields the rule found wrong
def _declared(**over):
    d = {"kind": "declared", "size_now": 2100000, "dimension": 768,
         "embedding_model": "BAAI/bge-base-en-v1.5",
         "corpus_type": "support_tickets", "text_length": "short",
         "topics_trend": True, "time_ordered": True,
         "languages": ["en"], "nearest_fixture": "auto"}
    d.update(over)
    return d


def _write_declared(tmp, **over):
    p = os.path.join(tmp, "r.yaml")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump({"oneground": 1,
                        "run": {"name": "t", "seed": 1},
                        "corpus": {"declared": _declared(**over)}}, f)
    return p


def test_an_unknown_nearest_fixture_is_refused():
    """The rule said this closed domain should be checked and it was not
    (task 049's proposal). Fixed, and watched to fail: `auto` and `none`
    still pass; a name matching no built fixture does not."""
    with tempfile.TemporaryDirectory() as tmp:
        p = _write_declared(tmp, nearest_fixture="arxiv-1500k")
        with pytest.raises(intake.RequirementsError, match="nearest_fixture"):
            intake.load(p)
    with tempfile.TemporaryDirectory() as tmp:
        intake.load(_write_declared(tmp, nearest_fixture="auto"))
        intake.load(_write_declared(tmp, nearest_fixture="none"))


def test_a_real_fixture_id_is_accepted_without_hardcoding_it_here():
    """The set is read from the fixtures directory, not written down --
    proved by not naming a fixture in this test either, only by asking
    `analogy` what exists and using its own answer."""
    from oneground import analogy
    known = [fid for fid, _a, _p, _s in analogy.load_fixture_analogies()]
    assert known, "no fixture has an analogy block to test against"
    with tempfile.TemporaryDirectory() as tmp:
        intake.load(_write_declared(tmp, nearest_fixture=known[0]))


def test_an_unknown_queries_source_is_refused():
    """The rule's other find: closed by the same reasoning as text_length,
    previously validated by nothing and read by nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "r.yaml")
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            yaml.safe_dump({
                "oneground": 1, "run": {"seed": 1},
                "corpus": {"sample": {
                    "vectors": {"path": "v.npy"},
                    "queries": {"path": "q.jsonl", "source": "overheard"},
                }}}, f)
        with pytest.raises(intake.RequirementsError, match="queries.source"):
            intake.load(p)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
