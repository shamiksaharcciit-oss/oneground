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

# ============================================================ the front doors
# Over HTTP, because "the form writes the file" is a property of the surface
# and not only of the writer beneath it.
import http.client                                            # noqa: E402
import json as _json                                          # noqa: E402
import tempfile                                               # noqa: E402

from oneground.lab import server                              # noqa: E402

TOKEN = "t" * 32


def _ui(directory):
    """A `oneground ui` session: a directory of runs, and the write half."""
    return server.LabServer(runs_dir=directory, token=TOKEN, port=0).start()


def _post(lab, path, body, token=TOKEN, method="POST"):
    conn = http.client.HTTPConnection("127.0.0.1", lab.port, timeout=30)
    headers = {"Host": f"127.0.0.1:{lab.port}",
               "Content-Type": "application/json"}
    if token is not None:
        headers[server.TOKEN_HEADER] = token
    raw = _json.dumps(body).encode("utf-8") if body is not None else b""
    conn.request(method, path, body=raw, headers=headers)
    r = conn.getresponse()
    status, payload = r.status, r.read()
    conn.close()
    try:
        return status, _json.loads(payload)
    except ValueError:
        return status, payload


def _fetch(lab, path, method="GET"):
    conn = http.client.HTTPConnection("127.0.0.1", lab.port, timeout=30)
    conn.request(method, path, headers={
        "Host": f"127.0.0.1:{lab.port}", server.TOKEN_HEADER: TOKEN})
    r = conn.getresponse()
    status, payload = r.status, r.read()
    conn.close()
    try:
        return status, _json.loads(payload)
    except ValueError:
        return status, payload


def test_the_three_doors_over_http_end_at_the_same_file():
    """The acceptance line, through the surface rather than under it."""
    with tempfile.TemporaryDirectory() as tmp:
        lab = _ui(tmp)
        try:
            # door one: type it
            status, typed = _post(lab, "/api/compose/preview",
                                  {"state": TIER1})
            assert status == 200, typed

            # door three: take the template, then fill it
            status, template = _fetch(lab, "/api/compose/template")
            assert status == 200 and "oneground" in template["text"]

            # door two: upload what door one produced
            status, opened = _post(lab, "/api/compose/open",
                                   {"text": typed["text"]})
            assert status == 200, opened
            assert opened["refusal"] is None
            status, uploaded = _post(lab, "/api/compose/preview",
                                     {"state": opened["state"]})
            assert status == 200

            assert typed["document"] == uploaded["document"]
            assert typed["text"] == uploaded["text"]

            # and saving lands one file, named relative to the session's dir
            status, saved = _post(lab, "/api/compose/write",
                                  {"state": TIER1, "path": "r.yaml"})
            assert status == 200, saved
            assert saved["path"] == "r.yaml"
            assert os.path.isfile(os.path.join(tmp, "r.yaml"))
        finally:
            lab.stop()


def test_an_uploaded_file_is_refused_against_a_field_not_a_position():
    """Door two validates on arrival, and the error names the field it
    belongs to -- the whole difference between arriving in a form and
    arriving at a traceback."""
    with tempfile.TemporaryDirectory() as tmp:
        lab = _ui(tmp)
        try:
            bad = ("oneground: 1\n"
                   "run: {name: x, seed: 1}\n"
                   "corpus:\n  sample:\n"
                   "    text: {path: ./docs.jsonl}\n"
                   "    queries: {path: ./q.npy}\n")
            status, out = _post(lab, "/api/compose/open", {"text": bad})
            assert status == 200, out
            assert out["field"] == "corpus.sample.text.model"
            assert "neither" in out["refusal"]
            # the refusal is the CLI's sentence, not the form's
            assert "oneground will not choose one for you" in out["refusal"]

            # A defect in `intake`, surfaced rather than hidden: a
            # `corpus:` holding a list crashes `load()` with
            # AttributeError instead of refusing, because `load()`
            # checks that the DOCUMENT is a mapping and never that a
            # block inside it is. The form answers rather than dropping
            # the connection, and says whose defect it is. The repair
            # belongs to `intake`, not to the form that found it.
            status, out = _post(lab, "/api/compose/open",
                                {"text": "corpus: [this is a list]\n"})
            assert status == 500, out
            assert "defect in the tool" in out["error"]
            assert out["raised"].startswith("AttributeError")
        finally:
            lab.stop()


def test_a_file_that_is_not_yaml_is_named_by_line_not_by_stack():
    with tempfile.TemporaryDirectory() as tmp:
        lab = _ui(tmp)
        try:
            status, out = _post(lab, "/api/compose/open",
                                {"text": "run:\n  name: [unclosed\n"})
            assert status == 400, out
            assert "line" in out["refusal"]
        finally:
            lab.stop()


def test_the_write_endpoint_refuses_in_the_cli_s_words_and_writes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        lab = _ui(tmp)
        try:
            state = dict(TIER1)
            state["corpus.sample.text.path"] = "./docs.jsonl"
            status, out = _post(lab, "/api/compose/write",
                                {"state": state, "path": "r.yaml"})
            assert status == 400, out
            assert "are both set" in out["refusal"]
            assert os.listdir(tmp) == []
        finally:
            lab.stop()


def test_a_write_cannot_land_outside_the_directory_the_session_serves():
    with tempfile.TemporaryDirectory() as tmp:
        inner = os.path.join(tmp, "runs")
        os.mkdir(inner)
        lab = _ui(inner)
        try:
            for escape in ("../escaped.yaml", "../../escaped.yaml",
                           os.path.join(tmp, "escaped.yaml")):
                status, out = _post(lab, "/api/compose/write",
                                    {"state": TIER1, "path": escape})
                assert status == 400, (escape, out)
                assert "outside the directory" in out["error"], escape
            assert os.listdir(tmp) == ["runs"]
            assert os.listdir(inner) == []
        finally:
            lab.stop()


def test_a_lab_session_over_one_run_refuses_every_write():
    """Reading a run can never trigger a write, enforced rather than
    intended: the write half belongs to `oneground ui`."""
    from oneground.lab import test_server as S
    with tempfile.TemporaryDirectory() as tmp:
        wd = S._workdir(tmp, "run", 0.2, receipts=True)
        lab = S._lab(wd)
        try:
            status, out = _post(lab, "/api/compose/write",
                                {"state": TIER1, "path": "r.yaml"},
                                token=S.TOKEN)
            assert status == 405, out
            assert "reads and never writes" in out["error"]
            before = sorted(os.listdir(wd))
            status, _ = _post(lab, "/api/compose/preview", {"state": TIER1},
                              token=S.TOKEN)
            assert status == 405
            assert sorted(os.listdir(wd)) == before
        finally:
            lab.stop()


def test_a_read_route_cannot_be_posted_and_a_write_route_cannot_be_got():
    """The split is in the table rather than in a conditional somebody has to
    remember to write."""
    with tempfile.TemporaryDirectory() as tmp:
        lab = _ui(tmp)
        try:
            status, out = _post(lab, "/api/runs", {})
            assert status == 405 and "read-only" in out["error"]
            status, out = _fetch(lab, "/api/compose/write")
            assert status == 405 and "answers POST" in out["error"]
        finally:
            lab.stop()


def test_the_write_half_still_needs_the_token():
    with tempfile.TemporaryDirectory() as tmp:
        lab = _ui(tmp)
        try:
            status, out = _post(lab, "/api/compose/write",
                                {"state": TIER1, "path": "r.yaml"},
                                token=None)
            assert status == 403 and "token" in out["error"]
            assert os.listdir(tmp) == []
        finally:
            lab.stop()


def test_an_oversized_body_is_refused_before_it_is_parsed():
    with tempfile.TemporaryDirectory() as tmp:
        lab = _ui(tmp)
        try:
            huge = {"state": {"run.name": "x" * (server.MAX_BODY + 10)}}
            status, out = _post(lab, "/api/compose/write", huge)
            assert status == 413, out
        finally:
            lab.stop()


def test_the_form_renders_itself_from_the_declaration():
    """The form carries no labels of its own. It asks for the table, which is
    what makes one declaration rather than an agreement between two."""
    with tempfile.TemporaryDirectory() as tmp:
        lab = _ui(tmp)
        try:
            status, out = _fetch(lab, "/api/compose/fields")
            assert status == 200
            offered = {f["name"]: f for f in out["fields"]}
            assert len(offered) == len(fields.FIELDS)
            for param in fields.FIELDS:
                assert offered[param.name]["note"] == param.note
            assert len(out["outside_the_table"]) == 11
            assert offered["run.seed"]["required"] is True
            assert offered["corpus.declared.text_length"]["choices"] == [
                "short", "medium", "long"]
        finally:
            lab.stop()


def test_a_served_module_that_writes_stops_the_session_starting():
    """The write-path scan is load-bearing at startup, like the contract."""
    real = guard.check_write_path
    guard.check_write_path = lambda: {"runs.py": [(1, "write", "open(w)")]}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(server.LabRefused) as caught:
                server.LabServer(runs_dir=tmp, token=TOKEN, port=0)
            assert "open a file for writing" in str(caught.value)
            assert "compose.py" in str(caught.value)
    finally:
        guard.check_write_path = real

def test_required_is_its_own_declaration_and_not_the_family_default():
    """`Param.default is NO_DEFAULT` means *the family has no default for
    this key*. It does not mean *required*, and reading it that way labelled
    every optional field required -- `ids_path` was marked required directly
    above an explanation beginning "Optional."

    docs/PRACTICE.md section 4: a key whose meaning differs by file. The
    field was present, well-formed and plausible, which is why it took a
    browser to see.
    """
    optional = [p for p in fields.FIELDS
                if p.name not in fields.REQUIRED]
    assert optional, "every field cannot be required"
    # the field whose own note says it is optional is not required
    assert "corpus.sample.vectors.ids_path" not in fields.REQUIRED
    assert fields.BY_NAME["corpus.sample.vectors.ids_path"].note         .startswith("Optional")
    # and the ones intake actually refuses when absent are
    for name in ("run.seed", "corpus.sample.queries.path",
                 "corpus.declared.size_now", "corpus.declared.dimension"):
        assert name in fields.REQUIRED, name


def test_every_required_condition_is_written_in_one_vocabulary():
    """`REQUIRED` and `belongs_to` are read by one evaluator in the form, so
    a condition in one must be a condition the other could hold."""
    for name, when in fields.REQUIRED.items():
        assert name in fields.BY_NAME, name
        owner, wanted = when
        assert isinstance(owner, str) and owner
        assert wanted in fields.SENTINELS or isinstance(wanted, tuple), name


def test_the_required_field_of_a_block_is_offered_from_empty():
    """A form that hides the one field a user must fill, while showing the
    optional ones beside it, is internally consistent and wrong. Found in a
    browser: `queries.path` was conditional on the block being non-empty."""
    for name in ("corpus.sample.vectors.path", "corpus.sample.text.path",
                 "corpus.sample.queries.path"):
        assert fields.BY_NAME[name].belongs_to is None, name

def test_the_server_makes_no_request_of_its_own():
    """The last unbroken promise in `server.py`'s own list, and the one the
    write half puts under pressure: a job has to be enqueued and the
    supervisor owns the job list.

    Held until it is ruled on, and held by a check rather than by the
    docstring alone -- which is the lesson from the two bullets beside it
    that stopped being true without anything noticing. Parsed, not searched:
    the header discusses making requests at length, and a text match would
    find the discussion.
    """
    import ast
    import os
    from oneground.lab import guard

    outbound = {"urlopen", "urlretrieve", "Request", "HTTPConnection",
                "HTTPSConnection", "create_connection", "connect", "get",
                "post", "put", "delete", "request"}
    owners = {"urllib", "requests", "httpx", "socket", "http"}
    problems = []
    for name in guard.TRANSPORT_MODULES + guard.CONTRACT_MODULES             + guard.WRITE_MODULES:
        path = os.path.join(guard.LAB_DIR, name)
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if isinstance(fn, ast.Attribute) and fn.attr in outbound                     and isinstance(fn.value, ast.Name)                     and fn.value.id in owners:
                problems.append((name, node.lineno,
                                 f"{fn.value.id}.{fn.attr}()"))
    assert problems == [], (
        "a served module makes a request of its own: " + repr(problems))

def test_a_failing_replace_leaves_no_temp_behind(tmp_path, monkeypatch):
    """The last step was outside the cleanup.

    Every failure in `write` removed the temp file except the one in
    `os.replace` itself, which sat after the handler -- so a sharing
    violation, the ordinary Windows failure there, left a stray
    `.oneground-write` in the runs directory. Watched failing: the mutant
    makes the replace raise and asserts the directory comes back empty.
    """
    target = str(tmp_path / "r.yaml")
    real = os.replace

    def refuses(a, b):
        if str(a).endswith(compose.TEMP_SUFFIX):
            raise OSError(32, "used by another process")
        return real(a, b)

    monkeypatch.setattr(os, "replace", refuses)
    with pytest.raises(OSError):
        compose.write(compose.document(TIER1), target)
    assert os.listdir(tmp_path) == [], "the guard left its own temp behind"

def test_a_refused_request_does_not_also_perform_the_action():
    """The token check must STOP the request, not merely answer it.

    `_refuse_unless_addressed` returned `self.send(...)`, `send` has no
    return statement, so callers testing `if refusal is not None` never
    stopped: **the 403 went out and the handler carried on and did the
    work.** An unauthenticated caller got a refusal and the action.

    It showed up only as an intermittent `os.listdir(tmp) == []` failure,
    because the write raced the session teardown and lost most of the time.
    That assertion was the single piece of evidence, and it was twice
    explained away as a connection-reset flake before it was chased.

    So this asserts the consequence rather than the status: refused and
    nothing happened, over enough attempts that the race cannot hide it.
    """
    for _ in range(12):
        with tempfile.TemporaryDirectory() as tmp:
            lab = _ui(tmp)
            try:
                status, out = _post(lab, "/api/compose/write",
                                    {"state": TIER1, "path": "r.yaml"},
                                    token=None)
                assert status == 403, out
            finally:
                lab.stop()
            assert os.listdir(tmp) == [], (
                "a refused request performed the action anyway")


def test_a_wrong_host_also_stops_the_request():
    """The other half of the same guard, which had the same defect."""
    with tempfile.TemporaryDirectory() as tmp:
        lab = _ui(tmp)
        try:
            conn = http.client.HTTPConnection("127.0.0.1", lab.port,
                                              timeout=30)
            conn.request("POST", "/api/compose/write",
                         body=_json.dumps({"state": TIER1,
                                           "path": "r.yaml"}).encode(),
                         headers={"Host": "not-this-one.test",
                                  "Content-Type": "application/json",
                                  server.TOKEN_HEADER: TOKEN})
            r = conn.getresponse()
            assert r.status == 403, r.status
            r.read()
            conn.close()
        finally:
            lab.stop()
        assert os.listdir(tmp) == []
