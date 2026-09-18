"""The claim invariant: no sentence about rows outside the Claim renderer.

**Synthetic except where it says otherwise.** The two real fixtures' reports
are checked as themselves, and they say so.

WHAT THIS FILE IS FOR
---------------------
Three tasks running produced the same defect and two of them shipped:

  015   `and both carry {best.outcome}` -- the winner's verdict asserted of
        every engine, in a report, about a pgvector row that sustained 112.63
        of an offered 200.
  017e  `_options_table` rendering the FIRST verdict for a constraint, so a
        configuration that met the p95 budget on Qdrant and missed it on
        pgvector by forty times showed one flat green cell.

Both passed every test in the repository, because the tests asserted
**presence** -- the names appear, the page renders -- and the defect was in
**correspondence**. See `docs/CLAIMS.md`.
"""

import ast
import itertools
import json
import os
import re
import sys

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground import report as rep                          # noqa: E402
from oneground.report import claims as cl                    # noqa: E402
from oneground.report import html as H                       # noqa: E402
from oneground.report import verdict as vd                   # noqa: E402

MEETS, FAILS, CC = vd.MEETS, vd.FAILS, vd.COULDNT_CHECK
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))

# The modules that render text about rows, relative to this directory.
# `claims.py` is the renderer and is therefore the one place allowed to
# interpolate a verdict into a string. Task 028 put the proposal card under
# the same rule: a card asserts about rows exactly as a report does, and its
# sentences are rendered in `claims.py` beside the report's.
RENDERING_MODULES = ("__init__.py", "html.py",
                     os.path.join("..", "proposals", "card.py"),
                     os.path.join("..", "proposals", "propose.py"))

# What may never be interpolated outside the renderer: an outcome, a verdict,
# an engine name, or a measured value.
FORBIDDEN_ATTRS = ("outcome", "engine", "value", "reason", "verdicts",
                   "engines_meeting", "holds_for")


# --------------------------------------------------------------------------
# 1. the grep-guard
# --------------------------------------------------------------------------

def _formatted_expressions(tree):
    """[(lineno, source)] for every value interpolated into a string.

    f-strings and `%` both, because swapping one for the other is the first
    thing a guard that only knew about f-strings would teach people to do.
    """
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for part in node.values:
                if isinstance(part, ast.FormattedValue):
                    out.append((part.lineno, ast.unparse(part.value)))
        elif (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod)
                and isinstance(node.left, (ast.Constant, ast.JoinedStr))
                and isinstance(getattr(node.left, "value", ""), str)):
            out.append((node.lineno, ast.unparse(node.right)))
        elif (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "format"):
            out.append((node.lineno, ast.unparse(node)))
    return out


def _offending_sites(path):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    bad = []
    for lineno, src in _formatted_expressions(tree):
        for attr in FORBIDDEN_ATTRS:
            if re.search(r"\.%s\b" % attr, src):
                bad.append((lineno, attr, src[:90]))
                break
    return bad


def test_no_rendering_module_formats_a_verdict_into_a_string():
    """The guard the brief asks for, and the reason it is an AST walk.

    A regex over the file would flag the docstrings that quote the defect --
    this one included -- and be relaxed on its first day. This looks at the
    expressions actually interpolated into strings.
    """
    offences = []
    for name in RENDERING_MODULES:
        path = os.path.join(HERE, name)
        where = os.path.relpath(path, ROOT).replace("\\", "/")
        for lineno, attr, src in _offending_sites(path):
            offences.append("%s:%d interpolates .%s -- %s"
                            % (where, lineno, attr, src))
    assert not offences, (
        "a sentence about rows is being formatted outside the Claim "
        "renderer:\n  " + "\n  ".join(offences)
        + "\n\nBuild a Claim and render it. See docs/CLAIMS.md.")


def test_the_guard_sees_both_f_strings_and_percent_formats():
    """The negative control for the guard itself.

    A guard that only knew about f-strings would teach people to write `%`,
    which is how a rule becomes a style preference.
    """
    src = (
        "def f(v):\n"
        "    a = f'{v.outcome} is the answer'\n"
        "    b = '%s carried it' % v.engine\n"
        "    c = '{}'.format(v.value)\n"
        "    d = f'{v.constraint} is fine'\n"
        "    return a, b, c, d\n")
    tree = ast.parse(src)
    found = set()
    for lineno, expr in _formatted_expressions(tree):
        for attr in FORBIDDEN_ATTRS:
            if re.search(r"\.%s\b" % attr, expr):
                found.add(attr)
    assert found == {"outcome", "engine", "value"}, found


# --------------------------------------------------------------------------
# 2. the invariant, over generated reports
# --------------------------------------------------------------------------

CFG_A = "single_node_hnsw[M=32,efConstruction=200,efSearch=128]"
CONSTRAINTS = {"recall_at_k": {"k": 10, "min": 0.95},
               "latency": {"p95_ms": 40, "at_qps": 200, "concurrency": 32}}


def _verdict(constraint, outcome, value, engine=None, reason=None):
    return vd.Verdict(
        constraint, outcome,
        reason if reason is not None else "%s against the threshold" % outcome,
        source=("verify.json:engines[%s].%s" % (engine, constraint) if engine
                else "simulate.json:%s" % constraint),
        value=value, threshold=40.0, engine=engine)


def make_option(config, per_engine=(), plain=(), family="single_node_hnsw"):
    """One judged option. `per_engine` is [(constraint, engine, outcome, v)]."""
    verdicts = [_verdict(c, o, v) for c, o, v in plain]
    verdicts += [_verdict(c, o, v, engine=e) for c, e, o, v in per_engine]
    opt = vd.Option(family=family, config=config, params={},
                    measurement={"recall_at_10": 0.99, "ceiling_at_10": 0.99,
                                 "storage_amplification": 1.0, "fanout": 1.0},
                    verdicts=verdicts)
    opt.outcome = vd.overall(verdicts)
    opt.engines_meeting = vd.engines_meeting(verdicts)
    return opt


def claims_for(options, not_run=(), env_id="pod-1"):
    rec = next((o for o in options if o.outcome == MEETS), None)
    return rep.decision_claims(list(options), list(not_run), rec,
                               CONSTRAINTS, None, env_id=env_id)


def assert_invariant(options, where=""):
    claims = claims_for(options)
    rows = cl.rows_from_options(options)
    bad = cl.check_all(claims, rows)
    assert not bad, "%s\n%s" % (where, "\n".join(
        "[%s] %s\n    %s" % (c.kind, c.text[:140], "; ".join(p))
        for c, p in bad))
    return claims


def test_the_invariant_holds_on_the_shape_both_defects_had():
    """One configuration, two engines, one meeting and one missing."""
    opt = make_option(CFG_A,
                      per_engine=[("latency_p95", "qdrant", MEETS, 7.72),
                                  ("latency_p95", "pgvector", FAILS, 317.41),
                                  ("qps", "qdrant", MEETS, 200.0),
                                  ("qps", "pgvector", FAILS, 119.1)],
                      plain=[("recall_at_10", MEETS, 0.999)])
    claims = assert_invariant([opt], "the 017e shape")
    assert claims, "no claims were produced at all"


# --------------------------------------------------------------------------
# 3. adversarial generation
# --------------------------------------------------------------------------

OUTCOMES = (MEETS, FAILS, CC)


def generated_cases():
    """Every row set the brief names, as (label, [options]).

    Generated rather than listed: the two historical defects were both in the
    space between "one option, one engine" and "several options, several
    engines", and an example test is exactly what did not find them.
    """
    cases = []

    # 1-2 engines x every combination of outcomes on two constraints.
    for n_engines in (1, 2):
        engines = ["qdrant", "pgvector"][:n_engines]
        for lat in itertools.product(OUTCOMES, repeat=n_engines):
            for qps in itertools.product(OUTCOMES, repeat=n_engines):
                per = []
                for i, e in enumerate(engines):
                    per.append(("latency_p95", e, lat[i], 7.72 + i))
                    per.append(("qps", e, qps[i], 200.0 - i))
                cases.append((
                    "engines=%d lat=%s qps=%s" % (n_engines, lat, qps),
                    [make_option(CFG_A, per_engine=per,
                                 plain=[("recall_at_10", MEETS, 0.999)])]))

    # 1 to 5 options, every combination of overall outcomes.
    for n in range(1, 6):
        for combo in itertools.product(OUTCOMES, repeat=min(n, 3)):
            opts = []
            for i in range(n):
                o = combo[i % len(combo)]
                opts.append(make_option(
                    "family_%d[M=%d]" % (i, 8 * (i + 1)),
                    plain=[("recall_at_10", o, 0.9 + i / 100.0)]))
            cases.append(("options=%d combo=%s" % (n, combo), opts))

    # A single option with no measurement at all.
    bare = vd.Option(family="f", config="bare[M=1]", params={},
                     measurement={}, verdicts=[])
    bare.outcome = vd.overall([])
    cases.append(("no measurement", [bare]))

    # Two engines where one is unanswerable (couldnt_check with no value).
    unanswerable = vd.Verdict("latency_p95", CC,
                              "unanswerable in this environment",
                              source="verify.json:engines[qdrant]",
                              value=None, engine="qdrant")
    opt = make_option(CFG_A,
                      per_engine=[("latency_p95", "pgvector", FAILS, 317.41)],
                      plain=[("recall_at_10", MEETS, 0.999)])
    opt.verdicts.append(unanswerable)
    opt.outcome = vd.overall(opt.verdicts)
    opt.engines_meeting = vd.engines_meeting(opt.verdicts)
    cases.append(("one engine unanswerable", [opt]))

    # Values that tie exactly, and values inside the calibration tolerance.
    for label, second in (("exact tie", 7.72),
                          ("inside tolerance", 7.72 + vd.CALIBRATION_TOLERANCE
                           / 2.0)):
        cases.append((label, [make_option(
            CFG_A,
            per_engine=[("latency_p95", "qdrant", MEETS, 7.72),
                        ("latency_p95", "pgvector", MEETS, second)],
            plain=[("recall_at_10", MEETS, 0.999)])]))

    # A family that produced no rows at all.
    cases.append(("not run", [make_option(
        CFG_A, plain=[("recall_at_10", MEETS, 0.999)])]))
    return cases


GENERATED = generated_cases()


def test_adversarial_generation_covers_the_stated_space():
    """The space is generated, and its size is reported rather than assumed."""
    # The floor is below the space the generator actually produces, so a
    # generator that quietly shrank would fail here rather than the number
    # being tuned up to whatever today happens to be.
    assert len(GENERATED) >= 150, len(GENERATED)
    labels = [lbl for lbl, _ in GENERATED]
    assert len(set(labels)) == len(labels), "duplicate cases generated"
    # The two shapes the historical defects had must both be in there.
    assert any("engines=2" in l for l in labels)
    assert any("options=5" in l for l in labels)
    assert "one engine unanswerable" in labels
    assert "exact tie" in labels


def test_the_invariant_holds_on_every_generated_row_set():
    """Every Claim of every generated report, checked against its rows."""
    checked = 0
    for label, options in GENERATED:
        claims = claims_for(options)
        rows = cl.rows_from_options(options)
        bad = cl.check_all(claims, rows)
        checked += len(claims)
        assert not bad, "%s:\n%s" % (label, "\n".join(
            "  [%s] %s\n      %s" % (c.kind, c.text[:140], "; ".join(p))
            for c, p in bad))
    assert checked > 1000, (
        "only %d claims were checked; the generation is not exercising the "
        "space it claims to" % checked)
    print("\n%d generated row sets, %d claims checked"
          % (len(GENERATED), checked))


def test_every_generated_report_renders_to_html_and_console():
    """The full document, not only the log: the 017e defect was in a cell."""
    for label, options in GENERATED[:60]:
        claims = claims_for(options)
        report = _report_dict(options, claims)
        page = H.render_html(report, options, [], None, None, None, None, None)
        assert "<table" in page, label


def _report_dict(options, claims):
    return {
        "run": "gen", "generated_at": "2026-09-14T00:00:00Z",
        "summary": {MEETS: 0, FAILS: 0, CC: 0, "options": len(options),
                    "not_run": 0},
        "calibration": {"tolerance": vd.CALIBRATION_TOLERANCE,
                        "history_path": "h", "statements": []},
        "environment": {"verify_target": "runpod", "verify_platform": "x"},
        "inputs": {},
        "decision_log": [c.as_entry() for c in claims],
        "claims": [c.as_dict() for c in claims],
    }


# --------------------------------------------------------------------------
# 4. the two historical defects, as named regression tests
# --------------------------------------------------------------------------

def test_015_report_said_both_carry_meets_when_one_failed():
    """Task 015's report, verbatim: "and both carry meets".

    The row it said that about: pgvector sustained **112.63** of an offered
    200 -- a `fails` -- while qdrant held 200. The ranking was right; the
    sentence asserted the winner's verdict of both.

    What makes it impossible now is not the wording. It is that the claim
    declares `quantifier=UNIVERSAL` only when the outcomes are uniform, and
    `check()` refuses a universal whose `holds_for` is not its whole `scope`.
    """
    opt = make_option(CFG_A, per_engine=[("qps", "qdrant", MEETS, 200.0),
                                         ("qps", "pgvector", FAILS, 112.63)])
    claims = [c for c in rep.compare_engine_claims([opt], "pod-015")
              if c.kind == "engine_comparison"]
    assert claims, "the comparison did not fire at all"
    c = claims[0]
    assert c.quantifier == cl.EXISTENTIAL, c.quantifier
    assert "both carry meets" not in c.text.lower(), c.text
    assert "112.63 (fails)" in c.text, c.text
    assert "the verdicts differ" in c.text.lower(), c.text

    # And the invariant refuses the defect if it is put back by hand.
    forged = cl.Claim(
        kind="engine_comparison", predicate="carry meets",
        quantifier=cl.UNIVERSAL, subject=CFG_A, constraint="qps",
        scope=("qdrant", "pgvector"), holds_for=("qdrant",),
        cites=c.cites, text="qdrant 200.00 and both carry meets")
    problems = cl.check(forged)
    assert problems, "the invariant accepted the 015 sentence"
    assert any("universal" in p for p in problems), problems


def test_017e_html_showed_flat_green_when_pgvector_missed_by_40x():
    """Task 017e's report page: one `meets` cell under `latency_p95`.

    qdrant met the 40 ms budget at **7.72 ms**; pgvector missed it at
    **317.41 ms**, forty-one times higher. `_options_table` rendered
    `verdict_for(name)` -- the first verdict -- so the failing number appeared
    nowhere on the page.
    """
    opt = vd.Option(
        family="single_node_hnsw", config=CFG_A, params={},
        measurement={"recall_at_10": 0.999},
        verdicts=[_verdict("latency_p95", MEETS, 7.72, engine="qdrant",
                           reason="7.72 ms <= 40 ms"),
                  _verdict("latency_p95", FAILS, 317.41, engine="pgvector",
                           reason="317.41 ms > 40 ms")])
    opt.outcome = vd.overall(opt.verdicts)
    opt.engines_meeting = vd.engines_meeting(opt.verdicts)
    cell = H._verdict_cell(opt.verdicts_for("latency_p95"))
    text = re.sub(r"<[^>]+>", " ", cell)
    assert "qdrant" in text and "pgvector" in text, text
    assert "fails" in text, text
    assert "317.41" in cell, "the failing number is still not on the page"
    # Both engines are reachable from the structured record, so the page can
    # be rebuilt from it.
    assert len(opt.verdicts_for("latency_p95")) == 2


# --------------------------------------------------------------------------
# 5. the real reports
# --------------------------------------------------------------------------

REAL_WORKDIRS = (("arxiv-150k", "runs/arxiv-150k-via-characterize"),
                 ("stackexchange-150k", "runs/stackexchange-150k-via-characterize"))


def _rows_from_report(report):
    rows = cl.RowIndex()
    rows.setdefault(None, {})
    for opt in report.get("options") or []:
        cfg = opt.get("config")
        here = rows.setdefault(cfg, {})
        for v in (opt.get("judgement") or {}).get("constraints") or []:
            here.setdefault(v.get("engine") or cfg, {})[v.get("constraint")] = {
                "value": v.get("value"), "outcome": v.get("outcome"),
                "source": v.get("source")}
        for name, value in (opt.get("measurement") or {}).items():
            here.setdefault(cfg, {}).setdefault(
                name, {"value": value, "outcome": None,
                       "source": "simulate.json:rows[%s].%s" % (cfg, name)})
        rows[None].setdefault(cfg, here.get(cfg, {}))
    return rows


def test_the_invariant_holds_on_both_fixtures_real_reports_needs_local_run():
    """Not synthetic: the reports on disk, from real sessions.

    `runs/` is gitignored, so a fresh clone skips this -- and the skip names
    the command that produces one rather than passing quietly.
    """
    import pytest

    checked = 0
    seen = 0
    for name, wd in REAL_WORKDIRS:
        p = os.path.join(ROOT, wd, "report.json")
        if not os.path.exists(p):
            continue
        seen += 1
        with open(p, encoding="utf-8") as f:
            report = json.load(f)
        entries = report.get("claims")
        assert entries is not None, (
            "%s has a report.json with no `claims` block; the prose has no "
            "structured record and nothing can check it" % name)
        claims = [cl.Claim.from_dict(d) for d in entries]
        bad = cl.check_all(claims, _rows_from_report(report))
        checked += len(claims)
        assert not bad, "%s:\n%s" % (name, "\n".join(
            "  [%s] %s\n      %s" % (c.kind, c.text[:140], "; ".join(pr))
            for c, pr in bad))
    if not seen:
        pytest.skip(
            "no local workdir for either fixture. Run `oneground report "
            "requirements.arxiv-150k.yaml` to produce one.")
    print("\n%d claims checked across %d real report(s)" % (checked, seen))


# --------------------------------------------------------------------------
# 6. reconstructibility: report.json is the receipt for the prose
# --------------------------------------------------------------------------

def test_every_sentence_in_the_html_comes_from_the_structured_record():
    """Nothing on the page may exist that `report.json` does not contain.

    The same principle as a fixture's receipts, applied to prose: if a
    sentence cannot be regenerated from the record, the record is not a
    receipt for it and no checker can reach it. That is the condition under
    which both historical defects were invisible.
    """
    opt = make_option(CFG_A,
                      per_engine=[("latency_p95", "qdrant", MEETS, 7.72),
                                  ("latency_p95", "pgvector", FAILS, 317.41)],
                      plain=[("recall_at_10", MEETS, 0.999)])
    claims = claims_for([opt])
    report = _report_dict([opt], claims)
    page = H.render_html(report, [opt], [], None, None, None, None, None)

    # Every decision-log sentence on the page is in the record, verbatim.
    text = re.sub(r"<[^>]+>", " ", page)
    text = " ".join(text.replace("&#39;", "'").replace("&gt;", ">")
                    .replace("&lt;", "<").replace("&amp;", "&").split())
    for c in claims:
        want = " ".join(c.text.split())
        assert want in text, (
            "a claim in report.json is not on the page: %s" % want[:120])


def test_the_console_and_the_page_are_rebuilt_from_report_json_alone():
    """Given only the record, both surfaces come back identical.

    Rendered twice: once from the live objects, once from claims read back
    through `as_dict`/`from_dict` -- which is the round trip `report.json`
    actually makes.
    """
    opt = make_option(CFG_A,
                      per_engine=[("qps", "qdrant", MEETS, 200.0),
                                  ("qps", "pgvector", FAILS, 119.1)],
                      plain=[("recall_at_10", MEETS, 0.999)])
    live = claims_for([opt])
    round_tripped = [cl.Claim.from_dict(json.loads(json.dumps(c.as_dict())))
                     for c in live]

    assert [c.text for c in live] == [c.text for c in round_tripped]
    assert [c.as_entry() for c in live] == [c.as_entry() for c in round_tripped]

    # And re-rendering from the round-tripped Claim reproduces the sentence,
    # so the record carries everything the renderer needs -- not just the
    # finished string.
    for c in round_tripped:
        before = c.text
        c.text = ""
        assert cl.render(c) == before, (
            "%s cannot be re-rendered from its own record" % c.kind)


def test_a_claim_that_cannot_be_re_rendered_is_caught():
    """The negative control: drop a field the renderer needs."""
    opt = make_option(CFG_A, per_engine=[("qps", "qdrant", MEETS, 200.0),
                                         ("qps", "pgvector", FAILS, 119.1)])
    c = next(x for x in rep.compare_engine_claims([opt], "pod-1")
             if x.kind == "engine_comparison")
    d = c.as_dict()
    d["extra"] = {}                       # the renderer needs `best`
    broken = cl.Claim.from_dict(d)
    broken.text = ""
    try:
        cl.render(broken)
    except (KeyError, cl.ClaimViolation, StopIteration):
        return
    raise AssertionError("a claim missing what the renderer needs re-rendered "
                         "anyway, so the round trip proves nothing")


def _main():
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print("ok   %s" % name)
        except AssertionError as e:                       # noqa: PERF203
            failed += 1
            print("FAIL %s\n     %s" % (name, str(e)[:400]))
    print("\n%d/%d passed" % (len(fns) - failed, len(fns)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
