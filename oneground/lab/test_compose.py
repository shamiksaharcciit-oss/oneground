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

# ------------------------------------------------- the log, streamed
def test_a_log_is_read_by_offset_and_only_the_new_bytes_come_back(tmp_path):
    """A `simulate` writes for minutes. Re-reading the file every few
    seconds would cost more to watch than to run, and would replace text a
    reader was in the middle of."""
    from oneground import jobs as jobsmod
    from oneground import supervisor as supmod

    sup = supmod.Supervisor(str(tmp_path))
    job = sup.enqueue("simulate", ["simulate", "runs/x"])
    os.makedirs(os.path.join(str(tmp_path), supmod.LOGS_DIR), exist_ok=True)
    path = os.path.join(str(tmp_path), job.log)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("first\n")

    lab = _ui(str(tmp_path))
    try:
        a = lab.job_log({"id": [job.id]})
        assert a["text"] == "first\n" and a["live"] is True
        with open(path, "a", encoding="utf-8", newline="") as f:
            f.write("second\n")
        b = lab.job_log({"id": [job.id], "since": [str(a["offset"])]})
        assert b["text"] == "second\n", "the whole file came back again"
        assert b["offset"] > a["offset"]
        # and nothing new is nothing, not a re-send
        c = lab.job_log({"id": [job.id], "since": [str(b["offset"])]})
        assert c["text"] == ""
        assert jobsmod.QUEUED == job.state
    finally:
        lab.stop()


def test_an_offset_past_the_end_says_the_log_was_replaced(tmp_path):
    """Empty and replaced are different answers. Returning nothing for a
    stale offset would draw as "no output" over a log that exists."""
    from oneground import supervisor as supmod
    from oneground.lab import runs as runsmod
    sup = supmod.Supervisor(str(tmp_path))
    job = sup.enqueue("simulate", ["simulate", "runs/x"])
    os.makedirs(os.path.join(str(tmp_path), supmod.LOGS_DIR), exist_ok=True)
    with open(os.path.join(str(tmp_path), job.log), "w",
              encoding="utf-8", newline="") as f:
        f.write("short\n")
    lab = _ui(str(tmp_path))
    try:
        out = lab.job_log({"id": [job.id], "since": ["99999"]})
        assert out["text"] is None
        assert "replaced" in out["absent"]
    finally:
        lab.stop()


def test_the_log_path_comes_from_the_record_not_the_request(tmp_path):
    """No part of a request ever reaches a filesystem path -- the rule this
    server has held since it was written. The id is matched against the job
    list and the path is read off the record."""
    lab = _ui(str(tmp_path))
    try:
        for attempt in ("../../etc/passwd", "logs/../../secret",
                        "20260101T000000Z-simulate-deadbeef"):
            with pytest.raises(ValueError) as caught:
                lab.job_log({"id": [attempt]})
            assert "no job" in str(caught.value), attempt
    finally:
        lab.stop()

# ================================================== the forward to the supervisor
# Task 046, option B. The page cannot reach the supervisor itself -- this
# server's CSP says `connect-src 'self'` -- so the server forwards, to one
# loopback address read from its own runs directory and nowhere else.


def _with_address(tmp, url, token="t"):
    import json as _j
    from oneground import supervisor as supmod
    with open(os.path.join(str(tmp), supmod.ADDRESS_NAME), "w",
              encoding="utf-8") as f:
        _j.dump({"url": url, "token": token, "pid": 1, "build": "x"}, f)


def test_the_target_is_read_from_supervisor_json_and_nowhere_else(tmp_path):
    """One source. Not an environment variable, not a flag, not a default:
    the file the supervisor writes into the directory this session serves."""
    from oneground import supervisor as supmod
    lab = _ui(str(tmp_path))
    try:
        with pytest.raises(ValueError) as caught:
            lab._forward_target("/enqueue")
        assert "no supervisor has announced itself" in str(caught.value)

        _with_address(tmp_path, "http://127.0.0.1:9999", token="abc")
        host, port, route, token = lab._forward_target("/enqueue")
        assert (host, port, route, token) == ("127.0.0.1", 9999,
                                              "/enqueue", "abc")
        assert lab.FORWARD_SOURCE == supmod.ADDRESS_NAME
    finally:
        lab.stop()


# Each case names the refusal it expects, rather than accepting any. "It
# refused" is the assertion that passes when the wrong thing refuses -- the
# empty url below is refused a step earlier, by `address()` declining a file
# with no usable url, and a looser assertion would have hidden that.
@pytest.mark.parametrize("url,expect", [
    ("http://example.com:80", "is not loopback"),
    ("http://10.0.0.5:8080", "is not loopback"),
    # A suffix of loopback is not loopback: `startswith("127.")` would accept
    # this, which is the classic way this check is got wrong.
    ("http://127.0.0.1.evil.test:80", "is not loopback"),
    ("http://[2001:db8::1]:80", "is not loopback"),
    ("https://127.0.0.1:443", "not a usable http url"),
    ("ftp://127.0.0.1", "not a usable http url"),
    ("http://127.0.0.1:8080/enqueue", "carries a path"),
    ("", "no supervisor has announced itself"),
])
def test_a_target_that_is_not_loopback_is_refused_at_construction(
        tmp_path, url, expect):
    """**The mutant.** Refused before anything is sent, so a bad address
    cannot become a request -- validating at the call would put the check and
    the send in two places, and the second is where a shortcut goes.
    """
    lab = _ui(str(tmp_path))
    try:
        _with_address(tmp_path, url)
        with pytest.raises(ValueError) as caught:
            lab._forward_target("/enqueue")
        assert expect in str(caught.value), (url, str(caught.value))
    finally:
        lab.stop()


def test_loopback_is_a_closed_set_not_a_prefix():
    from oneground.lab import server as srv
    assert set(srv.LabServer.LOOPBACK) == {"127.0.0.1", "::1", "localhost"}


def test_exactly_one_served_function_may_reach_off_this_process():
    """The narrowed promise, checked -- not dropped. And the declaration
    names the destination beside the call site, so both are read together."""
    from oneground.lab import guard
    assert guard.check_outbound() == {}
    assert set(guard.OUTBOUND_ALLOWED) == {
        ("server.py", "forward_to_supervisor")}
    why = guard.OUTBOUND_ALLOWED[("server.py", "forward_to_supervisor")]
    assert "supervisor.json" in why and "loopback" in why


@pytest.mark.parametrize("source,caught", [
    ("import http.client\ndef innocent():\n"
     "    return http.client.HTTPConnection('example.com', 80)\n", True),
    ("import urllib.request\ndef helper():\n"
     "    return urllib.request.urlopen('http://x')\n", True),
    ("import http.client\ndef forward_to_supervisor(p, b):\n"
     "    return http.client.HTTPConnection('127.0.0.1', 1)\n", False),
])
def test_the_outbound_scan_is_function_scoped(source, caught):
    """Function-scoped, because the permission is about where in the module
    the call may be. A second call in a second function is what this exists
    to catch, and a module-level allowance would not see it."""
    from oneground.lab import guard
    found = guard.outbound_violations(source, "<m>", module="server.py")
    assert bool(found) is caught, found


def test_the_permission_is_for_one_module_too():
    """The same function name in another served module is not permitted."""
    from oneground.lab import guard
    source = ("import http.client\ndef forward_to_supervisor(p, b):\n"
              "    return http.client.HTTPConnection('127.0.0.1', 1)\n")
    assert guard.outbound_violations(source, "<m>", module="runs.py")


def test_a_served_module_reaching_out_stops_the_session_starting(tmp_path):
    """Held at startup like the contract and the write path, and watched
    firing rather than observed not firing."""
    from oneground.lab import guard, server as srv
    real = guard.check_outbound
    guard.check_outbound = lambda: {"runs.py": [(7, "outbound",
                                                 "urlopen() in fetch()")]}
    try:
        with pytest.raises(srv.LabRefused) as caught:
            srv.LabServer(runs_dir=str(tmp_path), port=0)
        said = str(caught.value)
        assert "reach off this process" in said
        assert "server.py.forward_to_supervisor" in said
    finally:
        guard.check_outbound = real


def test_the_supervisor_still_checks_its_own_token(tmp_path):
    """The server forwards a request; it does not authorise one. A forward
    carrying the wrong token is refused by the supervisor, and its refusal
    comes back unchanged rather than being re-expressed here.
    """
    from oneground import supervisor as supmod
    sup = supmod.Supervisor(str(tmp_path))
    channel = supmod.Channel(sup).start()
    try:
        # the address file says the right place and the WRONG token
        _with_address(tmp_path, channel.url, token="not-the-token")
        lab = _ui(str(tmp_path))
        try:
            status, out = lab.forward_to_supervisor(
                "/enqueue", {"stage": "simulate",
                             "invocation": ["simulate", "x"]})
            assert status == 403, out
            assert "token is required" in out["error"]
            assert sup.read() == [], "a refused forward enqueued a job"
        finally:
            lab.stop()
    finally:
        channel.stop()


def test_a_forward_that_works_returns_the_supervisors_own_answer(tmp_path):
    from oneground import supervisor as supmod
    sup = supmod.Supervisor(str(tmp_path))
    channel = supmod.Channel(sup).start()
    try:
        _with_address(tmp_path, channel.url, token=channel.token)
        lab = _ui(str(tmp_path))
        try:
            status, out = lab.forward_to_supervisor(
                "/enqueue", {"stage": "simulate",
                             "invocation": ["simulate", "runs/x"]})
            assert status == 200, out
            assert out["job"]["state"] == "queued"
            assert [j.id for j in sup.read()] == [out["job"]["id"]]

            # and a refusal comes back as the supervisor's own words
            status, out = lab.forward_to_supervisor(
                "/enqueue", {"stage": "pod up", "invocation": ["pod", "up"]})
            assert status == 400
            assert "cannot be automated by accident" in out["refusal"]
        finally:
            lab.stop()
    finally:
        channel.stop()

def test_a_job_drawing_carries_no_absolute_path(tmp_path):
    """`runs.shown_dir`'s rule one artifact further out: keeping the
    absolute path out of the DRAWING means no renderer can leak it.

    The job record on disk keeps the real path -- that is evidence about
    where the work happened -- and what crosses to a page is the tail. It
    was the build footer that made this necessary: every row printed the
    full package directory, so a developer's home directory appeared in
    every screenshot of the page. Slice 1's header leak, in the newest
    surface, three weeks later.
    """
    from oneground import supervisor as supmod
    from oneground.lab import runs as runsmod
    sup = supmod.Supervisor(str(tmp_path))
    job = sup.enqueue("simulate", ["simulate", "runs/x"])
    job.build = str(tmp_path / "deep" / "oneground")
    sup._replace(job)

    lab = _ui(str(tmp_path))
    try:
        drawn = lab.job_list({})["jobs"][0]
        for field in ("build", "workdir"):
            assert drawn[field], field
            # The property, not the format: the absolute path is absent and
            # what remains is a tail `shown_dir` produced. Asserting a slash
            # count instead would have been asserting the helper's spelling,
            # which is not what this test is about -- and the first version
            # did, and failed on `.../deep/oneground`.
            assert str(tmp_path) not in drawn[field], (
                field + " carries the absolute path into the drawing")
            assert drawn[field] == runsmod.shown_dir(drawn[field]), (
                field + " is not a shown path")
        # and the record itself still has it, because that is evidence
        assert str(tmp_path) in sup.read()[0].build
    finally:
        lab.stop()

# =========================================== step 7: coverage and fidelity
# Acceptance, not guards: whether the form OFFERS every field and whether the
# explanation in the file is the string the form showed are properties of a
# pair of things, and no guard has access to intent.


def test_the_explanation_in_the_file_is_the_string_the_form_shows():
    """One string, not two that agree.

    Both the form and the writer read `fields.BY_NAME[...].note`, so this
    asserts there is one source rather than that two copies match -- which
    is the difference between a property and a coincidence somebody has to
    maintain.
    """
    from oneground.lab import server as srv
    lab_fields = srv.LabServer.compose_fields(None, {})["fields"]
    shown = {f["name"]: f["note"] for f in lab_fields}

    state = {p.name: "x" for p in fields.FIELDS if p.type is str}
    state["oneground"] = 1
    text = compose.render(compose.document(state))
    for name, note in shown.items():
        if name not in text.replace(":", "").split() and                 name.split(".")[-1] not in text:
            continue                     # not written for this state
        words = " ".join(note.split())[:40]
        assert words in " ".join(text.split()), (
            f"{name}: the form shows a note the file does not carry")


def test_the_writer_uses_the_strings_it_is_given():
    """The mutant for the one-string claim. If `render` reached for its own
    copy instead of the declaration, this would still show the real notes."""
    doc = compose.document(TIER1)
    text = compose.render(doc, explain=lambda name: "SENTINEL for " + name)
    assert "SENTINEL for run.seed" in text
    assert "Every draw in a run is seeded" not in text


def test_the_file_says_its_comments_are_not_data():
    """Stated in the file, once, at the top -- the front-door ruling's own
    requirement. A user editing a comment changes nothing, and nothing but
    the file itself is going to tell them."""
    text = compose.render(compose.document(TIER1))
    assert text.startswith("# Written by oneground.")
    assert "not read back" in text


def test_every_field_the_form_offers_can_be_written_and_read_back(tmp_path):
    """Coverage: everything in the table survives a real write through the
    guard, which is what makes 'the form offers it' mean anything."""
    state = {}
    for p in fields.FIELDS:
        if p.name.startswith("extraction") or p.name == "corpus.sample.text.path":
            continue                     # a different tier; covered below
        if p.choices:
            state[p.name] = str(list(p.choices)[0])
        elif p.type is bool:
            state[p.name] = "true"
        elif p.type is int:
            state[p.name] = "7"
        elif p.type is list:
            state[p.name] = "a, b"
        else:
            state[p.name] = "./x"
    state["corpus.declared.size_now"] = "10"
    state["corpus.declared.dimension"] = "8"
    doc = compose.document(state)
    written = compose.write(doc, str(tmp_path / "r.yaml"))
    with open(written, encoding="utf-8") as f:
        again = yaml.safe_load(f)
    assert again == doc, "a field the form offers did not survive the write"


def test_the_written_file_is_stable_for_the_same_answers(tmp_path):
    """Two files with the same content are the same bytes: the writer walks
    the declaration's order, not the mapping's. A file whose keys wander is
    a file nobody can diff."""
    a = compose.render(compose.document(TIER1))
    shuffled = dict(reversed(list(TIER1.items())))
    b = compose.render(compose.document(shuffled))
    assert a == b

def test_the_read_half_is_still_read_only_over_a_written_into_directory(
        tmp_path):
    """Step 8. Slice 1 proved the server writes nothing; this proves that
    writing runs did not make the reader mutable.

    The directory is written into first -- a requirements file through the
    guard, a job list, a log -- and then every read endpoint is exercised
    and the digests are compared. A read-only proof over an empty directory
    would be a weaker claim than the one slice 1 made.
    """
    import hashlib
    from oneground import supervisor as supmod

    # write into it, by all three paths this slice added
    compose.write(compose.document(TIER1), str(tmp_path / "r.yaml"))
    sup = supmod.Supervisor(str(tmp_path))
    job = sup.enqueue("simulate", ["simulate", "runs/x"])
    os.makedirs(os.path.join(str(tmp_path), supmod.LOGS_DIR), exist_ok=True)
    with open(os.path.join(str(tmp_path), job.log), "w",
              encoding="utf-8", newline="") as f:
        f.write("some output\n")

    def digests():
        out = {}
        for root, _d, files in os.walk(str(tmp_path)):
            for name in sorted(files):
                path = os.path.join(root, name)
                with open(path, "rb") as f:
                    out[os.path.relpath(path, str(tmp_path))] =                         hashlib.sha256(f.read()).hexdigest()
        return out

    before = digests()
    assert before, "nothing was written, so this proves nothing"

    lab = _ui(str(tmp_path))
    try:
        lab.check({})
        lab.job_list({})
        lab.job_targets({})
        lab.supervisor_address({})
        lab.compose_fields({})
        lab.compose_template({})
        lab.job_log({"id": [job.id]})
        lab.run_list({})
    finally:
        lab.stop()

    assert digests() == before, "a read endpoint changed the directory"

# ============================================ what this session says it can do
# Task 046. Every sentence the server says about its own powers is composed
# from `CAPABILITY`, keyed by the write routes `answer_write` mounts. These
# tests are the reason that is a guarantee rather than a convention.


def test_every_write_route_has_a_phrase_and_no_phrase_lacks_a_route():
    """**The structural half, and the whole point of the repair.**

    A route added without a phrase fails here, so describing a new capability
    is part of adding one. This is what the previous repair lacked: that one
    split the sentence by mode, which made mode changes visible and left
    every other kind of change invisible in a slightly more convincing way.
    """
    from oneground.lab import server as srv
    assert set(srv.WRITE_ENDPOINTS) == set(srv.CAPABILITY), (
        "a write route with no phrase, or a phrase with no route: "
        f"{set(srv.WRITE_ENDPOINTS) ^ set(srv.CAPABILITY)}")


def test_a_new_write_route_changes_the_sentence_with_nothing_else_edited():
    """**The mutant.** Adding a route and its phrase, and touching no
    sentence anywhere, changes both sentences -- which is the claim the
    repair makes and the one that was false of its predecessor.
    """
    from oneground.lab import server as srv
    before_check = srv.can_sentence("runs", "nothing")
    before_warn = srv.check_host("0.0.0.0", i_know=True, runs_dir="runs")
    assert "delete a run" not in before_check
    assert "delete a run" not in before_warn

    srv.WRITE_ENDPOINTS["/api/runs/delete"] = "run_delete"
    srv.CAPABILITY["/api/runs/delete"] = "delete a run"
    try:
        assert "delete a run" in srv.can_sentence("runs", "nothing")
        assert "delete a run" in srv.check_host("0.0.0.0", i_know=True,
                                                runs_dir="runs")
    finally:
        del srv.WRITE_ENDPOINTS["/api/runs/delete"]
        del srv.CAPABILITY["/api/runs/delete"]

    assert srv.can_sentence("runs", "nothing") == before_check
    assert srv.check_host("0.0.0.0", i_know=True, runs_dir="runs") == \
        before_warn


def test_the_network_warning_names_what_exposing_a_ui_session_hands_over():
    """The sentence read at the moment someone is asked to type `--i-know`.

    It said *"It still writes nothing and runs nothing"* for the whole of the
    slice that gave `ui` both -- the one place this claim could cost
    something, because it is the sentence that answers *is this safe to
    expose*. It is asserted by content rather than by wording: the powers
    have to be named, and the read-only claim must be gone.
    """
    from oneground.lab import server as srv
    warning = srv.check_host("0.0.0.0", i_know=True, runs_dir="runs")
    assert "writes nothing" not in warning
    assert "runs nothing" not in warning
    assert "not read-only" in warning
    for power in srv.CAPABILITY.values():
        if power is not None:
            assert power in warning, power


def test_a_lab_session_over_one_run_still_says_it_writes_and_runs_nothing():
    """And says it because no write route is mounted, not because the
    sentence says so. The claim is true for `oneground lab` and stays."""
    from oneground.lab import server as srv
    warning = srv.check_host("0.0.0.0", i_know=True, runs_dir=None)
    assert "It writes nothing and runs nothing." in warning
    assert srv.capabilities(None) == ()


def test_the_check_panel_agrees_with_the_routes_that_are_mounted(tmp_path):
    """Asked of a running server, both ways round.

    A `ui` session serves the enqueue route and must not say no job is
    created from the page; a `lab` session serves neither and must say so.
    Measured by asking the server rather than by reading the constant, since
    the defect being fixed was a constant that disagreed with the server.
    """
    lab = _ui(str(tmp_path))
    try:
        said = lab.check({})
        assert "/api/jobs/run" in _server_module().WRITE_ENDPOINTS
        assert "nothing" not in said["runs"], said["runs"]
        assert "start stages" in said["runs"]
        assert "requirements files" in said["writes"]
    finally:
        lab.stop()


def test_the_claim_that_went_stale_is_not_written_down_anywhere(tmp_path):
    """The sentence itself, as a string, in the served package.

    It had six homes and two of them were gained inside the slice that made
    it false. This is the check that would have caught that -- and it is
    scoped to what the code says about itself, not to prose about history,
    because `docs/PRACTICE.md` and the report both quote the dead sentence
    on purpose.
    """
    import os
    import re
    root = os.path.dirname(os.path.dirname(os.path.abspath(
        _server_module().__file__)))
    # Assembled rather than written, so this scan does not find itself.
    # A check whose only hit is the check is warning 1's `atexit` instance,
    # which is on the page three entries above the one this test is for.
    dead = re.compile(" ".join(
        ["no", "job,", "no", "session", "is", "created"]))
    guilty = []
    for folder, _dirs, names in os.walk(root):
        if "__pycache__" in folder:
            continue
        for name in names:
            if not name.endswith((".py", ".js", ".html")):
                continue
            path = os.path.join(folder, name)
            with open(path, encoding="utf-8") as f:
                if dead.search(f.read()):
                    guilty.append(os.path.relpath(path, root))
    assert guilty == [], guilty


def _server_module():
    from oneground.lab import server as srv
    return srv
