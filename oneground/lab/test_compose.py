"""The write path: one construction, one guard, one module that writes.

Task 046 step 1 and step 6. Every test here is about a property the brief
names, and the mutants are written against the guard's own code rather than a
restatement of it -- `docs/PRACTICE.md` section 2, warnings 3 and 5.
"""

import os

import pytest
import yaml

from oneground import intake
from oneground.intake import fields
from oneground.lab import compose, guard

# A Tier-1 file the CLI accepts. The paths need not exist: `load()` validates
# the document, and only `input_paths()` asks the filesystem anything.
TIER1 = {
    "oneground": 1,
    "run.name": "support-tickets",
    "run.seed": "20260910",
    "corpus.sample.vectors.path": "./data/sample.npy",
    "corpus.sample.queries.path": "./data/queries.npy",
}

TIER2 = {
    "oneground": 1,
    "corpus.declared.size_now": "2_100_000",
    "corpus.declared.dimension": "768",
    "corpus.declared.text_length": "short",
    "corpus.declared.languages": "en, nl",
}


# ------------------------------------------------- step 1: three paths, one file
def test_three_paths_produce_the_same_file_for_the_same_inputs(tmp_path):
    """The acceptance line, and the reason `D` is built from form state
    rather than by editing a loaded document.

    Fill-in-the-form and upload-and-edit are not compared on their bytes by
    luck: they converge because both end at `document()`. A file that arrives
    becomes *state*, and state is the only thing that becomes a document.
    """
    typed = compose.document(TIER1)
    written = compose.write(typed, str(tmp_path / "typed.yaml"))

    # the upload path: bytes in, state, document -- never an edit of the
    # mapping that was loaded
    with open(written, encoding="utf-8") as f:
        arrived = yaml.safe_load(f)
    uploaded = compose.document(compose.state_from_mapping(arrived))

    # the template path: the same construction over the same inputs
    templated = compose.document(dict(TIER1))

    assert typed == uploaded == templated
    assert compose.render(typed) == compose.render(uploaded)


def test_a_field_nobody_filled_in_is_absent_rather_than_null(tmp_path):
    """Writing `null` would make the file say something the user did not."""
    doc = compose.document(TIER2)
    assert "run" not in doc
    assert "sample" not in doc.get("corpus", {})
    text = compose.render(doc)
    assert "null" not in text
    # and the schema version is the one default that is always written,
    # because it is the file describing itself rather than a setting
    assert doc["oneground"] == 1


def test_the_form_hands_back_strings_and_the_declaration_types_them():
    doc = compose.document(TIER2)
    assert doc["corpus"]["declared"]["size_now"] == 2100000     # int, not str
    assert doc["corpus"]["declared"]["languages"] == ["en", "nl"]
    assert compose.document(TIER1)["run"]["seed"] == 20260910


# ------------------------------------------------------ step 6: the guard
def test_the_guard_runs_on_every_write_and_refuses_in_the_cli_s_words(
        tmp_path):
    """The guard's second job: if `D` round-trips through `load()` then `D`
    is in the set `load()` accepts, so the form cannot construct a document
    the CLI would refuse without being told at write time.

    `vectors.path` and `text.path` together is one of the six relational
    refusals the field table cannot carry. The guard carries it anyway.
    """
    state = dict(TIER1)
    state["corpus.sample.text.path"] = "./data/docs.jsonl"
    state["corpus.sample.text.model"] = "BAAI/bge-base-en-v1.5"
    target = str(tmp_path / "both.yaml")

    with pytest.raises(compose.WriteRefused) as caught:
        compose.write(compose.document(state), target)

    # the CLI's words, not the form's
    assert "are both set" in caught.value.refusal
    assert "which of the two produced the vectors" in caught.value.refusal
    # and nothing was left behind, whole or partial
    assert not os.path.exists(target)
    assert os.listdir(tmp_path) == []


def test_the_guard_catches_a_document_that_parses_but_lost_something(
        tmp_path):
    """**The measurement that retires the naive rule.** "The file must load
    without a refusal" is the obvious guard and it is nowhere near enough:
    `constraints` is never read by `intake.load()`, so a file with every
    constraint dropped loads without a word.

    The mutant drops the block after the document was built. The naive rule
    passes it; identity does not.
    """
    doc = dict(compose.document(TIER1))
    doc["constraints"] = {"recall_at_k": {"k": 10, "min": 0.9}}
    target = str(tmp_path / "lossy.yaml")

    def losing_render(d, explain=None):
        d = {k: v for k, v in d.items() if k != "constraints"}
        return yaml.safe_dump(d, sort_keys=False)

    real, compose.render = compose.render, losing_render
    try:
        # the naive rule would pass: the lossy bytes load without a refusal
        probe = str(tmp_path / "probe.yaml")
        with open(probe, "w", encoding="utf-8") as f:
            f.write(losing_render(doc))
        intake.load(probe)                      # no refusal -- that is the point
        os.remove(probe)

        with pytest.raises(compose.WriteRefused) as caught:
            compose.write(doc, target)
    finally:
        compose.render = real

    assert caught.value.refusal is None         # it parsed; it did not survive
    lost = dict((name, (a, b)) for name, a, b in caught.value.lost)
    assert "constraints.recall_at_k.k" in lost
    assert not os.path.exists(target)


def test_the_guard_leaves_no_temp_file_behind(tmp_path):
    state = dict(TIER1)
    state["corpus.sample.text.path"] = "./docs.jsonl"
    with pytest.raises(compose.WriteRefused):
        compose.write(compose.document(state), str(tmp_path / "r.yaml"))
    assert [p for p in os.listdir(tmp_path)
            if p.endswith(compose.TEMP_SUFFIX)] == []


def test_a_value_that_does_not_survive_yaml_is_refused_rather_than_changed(
        tmp_path):
    """`D` is a plain YAML-native mapping, and the guard is what makes that a
    rule rather than a convention: a tuple comes back a list and the write is
    refused at the point the tuple was introduced."""
    doc = dict(compose.document(TIER2))
    doc["run"] = {"name": "x", "seed": 1, "regions": ("eu-west",)}
    with pytest.raises(compose.WriteRefused) as caught:
        compose.write(doc, str(tmp_path / "tuple.yaml"))
    assert caught.value.lost is not None


# ------------------------------------- step 6: exactly one module may write
def test_exactly_one_module_in_the_served_package_writes():
    """The inverse of the read half's scan. Together the two say *exactly one
    module writes, and it is this one*, which neither says alone."""
    assert guard.check_write_path() == {}
    assert guard.WRITE_MODULES == ("compose.py",)
    assert guard.unclassified_modules() == []


@pytest.mark.parametrize("source,expected", [
    ('open(p, "w")', "open(..., 'w')"),
    ("open(p, mode='a')", "open(..., 'a')"),
    ('open(p, "x")', "open(..., 'x')"),
    ('open(p, "r+")', "open(..., 'r+')"),
    ("os.replace(a, b)", "os.replace()"),
    ("os.remove(a)", "os.remove()"),
    ("shutil.move(a, b)", "shutil.move()"),
    ("shutil.rmtree(a)", "shutil.rmtree()"),
    ("p.write_text(s)", "write_text()"),
    ("p.write_bytes(s)", "write_bytes()"),
])
def test_the_write_scan_finds_a_write_however_it_is_spelled(source, expected):
    """Mutants that run the scan's own code rather than a copy of it. Each
    one is a way a write could be smuggled into a served module."""
    found = guard.write_violations(source)
    assert [d for _, _, d in found] == [expected], (source, found)


@pytest.mark.parametrize("source", [
    'open(p)',                       # a read
    'open(p, "r")',                  # a read, said out loud
    's.replace("\\\\", "/")',        # the false positive the first scan had
    'parts = str(p).replace("a", "b").split("/")',
    'out["index.html"] = out["index.html"].replace(a, b)',
    'd.copy()',                      # a dict, not shutil
])
def test_the_write_scan_does_not_report_a_read_or_a_string_method(source):
    """The first version of this scan reported `server.py`, `runs.py` and
    `guard.py` as writing. All four hits were `str.replace("\\\\", "/")` in a
    path. A check that reports its own coverage gap as the subject's defect
    is warning 1, and this is the test that would have caught it."""
    assert guard.write_violations(source) == [], source


def test_an_open_whose_mode_cannot_be_read_is_reported_not_skipped():
    """A scan that cannot tell answers couldn't-check rather than passing.
    A served module has no reason to open a file with a computed mode."""
    found = guard.write_violations("open(p, mode)")
    assert len(found) == 1 and "cannot read" in found[0][2]


def test_the_permitted_writer_actually_writes():
    """The floor under the scan: if `compose.py` stopped writing, every test
    above would still pass and the guard would be guarding nothing. An empty
    finding list is only meaningful once the scan is known to look at
    something."""
    path = os.path.join(guard.LAB_DIR, "compose.py")
    with open(path, encoding="utf-8") as f:
        found = guard.write_violations(f.read(), path)
    kinds = {d for _, _, d in found}
    assert "open(..., 'w')" in kinds
    assert "os.replace()" in kinds


# ------------------------------------------------ the table names its gaps
def test_the_eleven_refusals_outside_the_table_are_named():
    """Named rather than silently missing, which is the acceptance line. An
    implementer who does not know they are excluded will believe the table is
    finishable and stop at eleven."""
    assert len(fields.OUTSIDE_THE_TABLE) == 11
    kinds = [kind for _, kind, _ in fields.OUTSIDE_THE_TABLE]
    assert kinds.count("not-a-field") == 4
    assert kinds.count("negated-set") == 1
    assert len([k for k in kinds
                if k in ("xor", "one-of", "implies", "uniqueness")]) == 6
    for name, kind, why in fields.OUTSIDE_THE_TABLE:
        assert name and kind and why


def test_every_declared_field_carries_an_explanation():
    """`note` is the human explanation, and a field without one would be a
    field the written file cannot explain."""
    for param in fields.FIELDS:
        assert param.note.strip(), param.name
        assert len(param.note) > 30, param.name


def test_a_presence_sentinel_answers_a_question_with_no_value_in_it():
    """The line that keeps the sentinels from being the thin end of a
    predicate: presence is a different question from membership, not a
    broader version of it."""
    for param in fields.FIELDS:
        if not param.belongs_to:
            continue
        owner, wanted = param.belongs_to
        assert isinstance(owner, str) and owner
        if wanted in fields.SENTINELS:
            continue                    # a presence question: no value in it
        assert isinstance(wanted, tuple) and wanted, param.name
