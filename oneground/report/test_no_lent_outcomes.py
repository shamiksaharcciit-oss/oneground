"""No generated surface may lend one engine's outcome to another.

**Synthetic throughout.** The verdicts here are written by hand to a shape
that has actually been measured -- 017e's arXiv session, where the same
configuration met the p95 budget on Qdrant at 7.72 ms and missed it on
pgvector at 317.41 ms -- but nothing in this file measures anything.

WHY THIS FILE EXISTS
--------------------
Task 017f removed `and both carry {best.outcome}` from `compare_engines`: a
sentence built from ONE verdict and phrased as if it covered several. It
shipped in task 015's report claiming "both carry meets" about a pgvector row
that sustained 112.63 of an offered 200.

`test_verdict.py` then pinned the property -- but only on `compare_engines`,
the one function that was wrong. Task 018 asked whether the rest of the report
had the same shape, and it did, in three more places:

  1. `html._options_table` rendered `Option.verdict_for(name)`, the FIRST
     verdict for a constraint. With two engines that is one engine's answer in
     a cell headed by the constraint alone. The 017e option rendered a flat
     green `meets` under `latency_p95` and pgvector's 317.41 ms appeared
     nowhere on the page.
  2. `html._recommendation` listed `latency_p95` twice, once green and once
     red, with no engine on either -- one constraint answered twice and
     contradictorily.
  3. The decision log's `meets` entry listed the meeting verdicts without
     their engines. `collapse_by_constraint` folds per-engine verdicts
     permissively and its docstring states the precondition: "it is only safe
     because the decision log names the engine every time". It did not.

So this file checks the property across every surface, and -- the part that
makes it more than three more tests -- it derives the list of surfaces from
the source rather than declaring it, so a new decision-log entry or a new HTML
section cannot be added without being covered.

Each check carries its negative control: the pre-018 rendering, reconstructed
inline, must be CAUGHT. A guard that passes against the bug it guards is
worthless.
"""

import ast
import os
import re
import sys
import warnings

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground import report as rep                          # noqa: E402
from oneground.report import html as H                       # noqa: E402
from oneground.report import verdict as vd                   # noqa: E402

MEETS, FAILS, CC = vd.MEETS, vd.FAILS, vd.COULDNT_CHECK
CFG = "single_node_hnsw[M=32,efConstruction=200,efSearch=128]"
ENGINES = ("qdrant", "pgvector")

HERE = os.path.dirname(os.path.abspath(__file__))


# --------------------------------------------------------------------------
# the phrases that ASSERT a shared outcome
# --------------------------------------------------------------------------
# Deliberately not "carry the same": the mixed-verdict sentence says "the
# verdicts differ", and an earlier version of the 017f list matched that
# denial as if it were a claim. A guard that cannot tell an assertion from its
# negation is worse than none.
UNIFORM_CLAIMS = ("both carry", "all carry", "each carry", "every engine",
                  "both meet", "both fail", "all 2 carry", "all 3 carry",
                  "all 2 meet", "all 3 meet")

# The denials, which contain some of the strings above and must not be read as
# claims. Removed from the text before the claim search.
DENIALS = ("not true of every engine",
           "meets every engine-scoped constraint on",
           "does not all carry",
           "do not all carry")


def _claims_uniformity(text):
    t = text.lower()
    for d in DENIALS:
        t = t.replace(d, " ")
    return [c for c in UNIFORM_CLAIMS if c in t]


def _strip_tags(html):
    return re.sub(r"<[^>]+>", " ", html)


# --------------------------------------------------------------------------
# the option under test
# --------------------------------------------------------------------------

def _v(constraint, outcome, reason, value, engine=None, threshold=None):
    return vd.Verdict(constraint, outcome, reason,
                      source=("verify.json:engines[%s]" % engine if engine
                              else "simulate.json"),
                      value=value, threshold=threshold, engine=engine)


def _option(latency=(MEETS, FAILS), qps=(MEETS, FAILS)):
    """One configuration judged on two engines, outcomes given per engine."""
    verdicts = [_v("recall_at_10", MEETS, "0.9990 >= 0.9500", 0.999,
                   threshold=0.95)]
    for engine, outcome, value, reason in (
            ("qdrant", latency[0], 7.72, "7.72 ms <= 40 ms"),
            ("pgvector", latency[1], 317.41, "317.41 ms > 40 ms")):
        verdicts.append(_v("latency_p95", outcome, reason, value,
                           engine=engine, threshold=40.0))
    for engine, outcome, value, reason in (
            ("qdrant", qps[0], 200.0, "200.00 >= 200"),
            ("pgvector", qps[1], 119.1, "119.10 < 200")):
        verdicts.append(_v("qps", outcome, reason, value, engine=engine,
                           threshold=200.0))
    o = vd.Option(family="single_node_hnsw", config=CFG,
                  params={"M": 32, "efConstruction": 200, "efSearch": 128},
                  measurement={"recall_at_10": 0.999, "ceiling_at_10": 0.999,
                               "storage_amplification": 1.0, "fanout": 1.0,
                               "est_memory_bytes": 6.7e8, "shards": 1},
                  verdicts=verdicts)
    o.outcome = vd.overall(o.verdicts)
    o.engines_meeting = vd.engines_meeting(o.verdicts)
    return o


CONSTRAINTS = {"recall_at_k": {"k": 10, "min": 0.95},
               "latency": {"p95_ms": 40, "at_qps": 200, "concurrency": 32}}


def _decision_log_text(opt):
    return " ".join(
        e["text"] for e in rep.decision_log(
            [opt], [], opt if opt.outcome == MEETS else None, CONSTRAINTS,
            None, env_id="pod-1"))


def _report_dict(opt):
    return {
        "run": "t", "generated_at": "2026-09-13T00:00:00Z",
        "summary": {vd.MEETS: 1, vd.FAILS: 0, vd.COULDNT_CHECK: 0,
                    "options": 1, "not_run": 0},
        "calibration": {"tolerance": 0.01, "history_path": "h.jsonl",
                        "statements": ["engine: none"]},
        "environment": {"verify_target": "runpod",
                        "verify_platform": "linux"},
        "inputs": {},
        "decision_log": rep.decision_log(
            [opt], [], opt if opt.outcome == MEETS else None, CONSTRAINTS,
            None, env_id="pod-1"),
    }


def _html_text(opt):
    report = _report_dict(opt)
    page = H.render_html(report, [opt], [], opt, None, None, None, None)
    return _strip_tags(page)


# --------------------------------------------------------------------------
# the surfaces, derived from the source rather than declared
# --------------------------------------------------------------------------

def _module_ast(mod):
    with open(mod.__file__, encoding="utf-8") as f:
        return ast.parse(f.read())


def _decision_log_kinds():
    """Every `add("<kind>", ...)` literal in the two log builders."""
    tree = _module_ast(rep)
    kinds = set()
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef):
            continue
        if fn.name not in ("decision_log", "_declared_log"):
            continue
        for node in ast.walk(fn):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "add"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                kinds.add(node.args[0].value)
    # `compare_engines` returns entries the log splices in under their own
    # kinds, so they are part of the same surface.
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and fn.name == "compare_engines":
            for node in ast.walk(fn):
                if isinstance(node, ast.Dict):
                    for k, v in zip(node.keys, node.values):
                        if (isinstance(k, ast.Constant) and k.value == "kind"
                                and isinstance(v, ast.Constant)):
                            kinds.add(v.value)
    return kinds


def _html_sections():
    """Every module-level function `render_html` splices into the page."""
    tree = _module_ast(H)
    defined = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    called = set()
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and fn.name == "render_html":
            for node in ast.walk(fn):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id in defined):
                    called.add(node.func.id)
    return called


# Surfaces this file drives. Each entry is checked against the derived sets
# below, so the registry cannot fall behind the code.
COVERED_LOG_KINDS = {
    "scope", "not_run", "fails", "meets_environment", "meets",
    "indistinguishable", "engine_comparison", "no_engine_comparison",
    "engines_meeting", "recommendation", "to_resolve",
    # Tier 2 (`_declared_log`): no engine is measured at all, so no verdict
    # can be lent. Driven by test_tier2.py; listed here so the derived-set
    # guard has something to match and a new tier-2 kind still shows up.
    "analogy", "capacity",
}
# Every function `render_html` splices into the page. The ones that render no
# verdict are listed rather than filtered out, so adding a section is a
# decision about this file rather than something that happens quietly.
COVERED_HTML_SECTIONS = {
    "_recommendation",      # per-constraint rows; each carries its engine
    "_options_table",       # one cell per constraint; carries every engine
    "_log",                 # the decision log, verbatim
    "_ground",              # characterization numbers; no verdict
    "_receipts",            # digests; no verdict
    "_calibration",         # citation; no verdict
    "_tokens_css",          # stylesheet
    "esc",                  # escaping
}


def test_the_registry_covers_every_decision_log_kind():
    """A new log entry cannot be added without being covered here.

    Derived from the source, not declared: this is the same move as
    `imagecheck.build_inputs` reading the Dockerfile's COPY sources rather
    than trusting a hand-listed trigger set.
    """
    derived = _decision_log_kinds()
    assert derived, "the AST walk found no decision-log kinds at all"
    missing = derived - COVERED_LOG_KINDS
    assert not missing, (
        "decision-log kinds with no coverage in this file: %s. Add them to "
        "COVERED_LOG_KINDS and make sure the property below drives them."
        % sorted(missing))
    stale = COVERED_LOG_KINDS - derived
    assert not stale, ("COVERED_LOG_KINDS names kinds that no longer exist: "
                       "%s" % sorted(stale))


def test_the_registry_covers_every_html_section():
    derived = _html_sections()
    assert derived, "the AST walk found no HTML sections at all"
    assert derived == COVERED_HTML_SECTIONS, (
        sorted(derived ^ COVERED_HTML_SECTIONS))


# --------------------------------------------------------------------------
# the property, over every surface
# --------------------------------------------------------------------------

def _surfaces(opt):
    """(name, text) for every place this option's verdicts become words.

    The HTML is listed SECTION BY SECTION rather than as one page. The page
    embeds the decision log, which names every engine, so a whole-page string
    contains "pgvector" no matter what the options table did -- and the first
    negative control proved it: the pre-018 table cell, restored, passed a
    check made against the whole page.
    """
    report = _report_dict(opt)
    names = []
    for v in opt.verdicts:
        if v.constraint not in names:
            names.append(v.constraint)
    return [
        ("decision_log", _decision_log_text(opt)),
        ("compare_engines", " ".join(
            e["text"] for e in rep.compare_engines([opt], "pod-1"))),
        ("runner_up_lines", "\n".join(rep.runner_up_lines(opt, [opt]))),
        ("html:_recommendation",
         _strip_tags(H._recommendation(report, opt))),
        ("html:_options_table",
         _strip_tags(H._options_table([opt], [], names))),
        ("html:_log", _strip_tags(H._log(report))),
    ]


def _units(opt):
    """(surface, one sentence or cell) -- the grain a claim is made at.

    A uniformity claim is about ONE constraint, so the check has to be made at
    the grain where a constraint and a claim sit together. Joining the whole
    log into one string makes "All 2 carry meets" about latency read as a
    claim about qps too, and the guard then fails on correct output -- which
    is how a guard gets relaxed into uselessness.
    """
    out = [("decision_log:" + e["kind"], e["text"])
           for e in rep.decision_log(
               [opt], [], opt if opt.outcome == MEETS else None, CONSTRAINTS,
               None, env_id="pod-1")]
    out += [("compare_engines:" + e["kind"], e["text"])
            for e in rep.compare_engines([opt], "pod-1")]
    out += [("runner_up_lines", line)
            for line in rep.runner_up_lines(opt, [opt])]
    # The page, cut at the boundaries it renders: list items, table cells and
    # the recommendation's per-constraint rows.
    page = H.render_html(_report_dict(opt), [opt], [], opt, None, None, None,
                         None)
    for chunk in re.split(r"</li>|</td>|</div>|</p>|</section>", page):
        text = _strip_tags(chunk).strip()
        if text:
            out.append(("html", text))
    return out


ENGINE_SCOPED = ("latency_p95", "qps")


def test_no_surface_claims_uniformity_unless_that_constraint_is_uniform():
    """The property, across every generated surface rather than one function.

    Checked per constraint: a sentence may only say "all carry X" about a
    constraint whose engines all carry X. And a uniformity claim that names no
    constraint at all is a defect of its own -- a reader cannot tell what it
    covers.
    """
    import itertools
    for latency in itertools.product([MEETS, FAILS, CC], repeat=2):
        for qps in itertools.product([MEETS, FAILS], repeat=2):
            opt = _option(latency=list(latency), qps=list(qps))
            uniform = {"latency_p95": len(set(latency)) == 1,
                       "qps": len(set(qps)) == 1}
            for name, unit in _units(opt):
                claimed = _claims_uniformity(unit)
                if not claimed:
                    continue
                named = [c for c in ENGINE_SCOPED if c in unit]
                assert named, (
                    "%s claims %s without naming the constraint it is about, "
                    "so a reader cannot tell what the claim covers:\n%s"
                    % (name, claimed, unit))
                for c in named:
                    assert uniform[c], (
                        "%s claimed %s about %s, whose engines carry %s:\n%s"
                        % (name, claimed, c,
                           list(latency) if c == "latency_p95" else list(qps),
                           unit))


def test_every_surface_that_shows_a_mixed_constraint_names_both_engines():
    """A constraint whose engines disagree must show both, wherever it shows.

    The `latency_p95` cell that read a flat green `meets` satisfied "does not
    claim uniformity" -- it made no claim at all, which is how it got through.
    What catches it is requiring the losing engine to be on the page.
    """
    opt = _option(latency=[MEETS, FAILS], qps=[MEETS, FAILS])
    for name, text in _surfaces(opt):
        if name == "runner_up_lines":
            continue                    # fires only for an indistinguishable set
        if "latency_p95" not in text:
            continue
        for engine in ENGINES:
            assert engine in text, (
                "%s shows latency_p95 without naming %s, whose verdict on it "
                "differs from the other engine's:\n%s" % (name, engine, text))


def test_each_engines_number_travels_with_its_own_verdict():
    opt = _option(latency=[MEETS, FAILS], qps=[MEETS, FAILS])
    text = _decision_log_text(opt)
    assert "qdrant 7.72 (meets)" in text, text
    assert "pgvector 317.41 (fails)" in text, text
    assert "qdrant 200.00 (meets)" in text, text
    assert "pgvector 119.10 (fails)" in text, text


# --------------------------------------------------------------------------
# the three sites, each with the pre-018 rendering as its negative control
# --------------------------------------------------------------------------

def test_the_options_table_cell_shows_every_engines_verdict():
    opt = _option(latency=[MEETS, FAILS], qps=[MEETS, FAILS])
    cell = H._verdict_cell(opt.verdicts_for("latency_p95"))
    text = _strip_tags(cell)
    # The cell's own outcome is the collapsed one, so the row agrees with its
    # overall column...
    assert text.strip().startswith("meets"), text
    # ...and both engines carry their own beneath it.
    assert "qdrant meets" in text, text
    assert "pgvector fails" in text, text
    assert "317.41" in cell, cell        # the losing number, in the title

    # NEGATIVE CONTROL: the pre-018 rendering, which took the first verdict.
    first = opt.verdicts_for("latency_p95")[0]
    old = ('<td class="v %s">%s</td>'
           % (H.OUTCOME_TOKEN[first.outcome], first.outcome))
    old_text = _strip_tags(old)
    assert "pgvector" not in old_text and "fails" not in old_text, (
        "the negative control is not the bug it is meant to be: %s" % old_text)


def test_a_single_unattributed_verdict_still_renders_the_plain_cell():
    """One verdict with no engine -- recall, storage -- is unchanged."""
    opt = _option()
    cell = H._verdict_cell(opt.verdicts_for("recall_at_10"))
    assert "by-engine" not in cell, cell
    assert "simulate.json" in cell, cell
    assert _strip_tags(cell).strip().startswith("meets"), cell


def test_the_recommendation_panel_names_the_engine_on_each_verdict():
    opt = _option(latency=[MEETS, FAILS], qps=[MEETS, FAILS])
    panel = H._recommendation(_report_dict(opt), opt)
    # Two latency_p95 rows, one green one red, each labelled.
    assert panel.count("latency_p95") == 2, panel
    assert 'class="rec-ce">qdrant<' in panel, panel
    assert 'class="rec-ce">pgvector<' in panel, panel
    # The unattributed one carries no engine label.
    body = panel.split("recall_at_10")[1][:120]
    assert "rec-ce" not in body, body


def test_the_meets_line_says_when_it_is_not_true_of_every_engine():
    opt = _option(latency=[MEETS, FAILS], qps=[MEETS, FAILS])
    line = [e for e in rep.decision_log([opt], [], opt, CONSTRAINTS, None,
                                        env_id="pod-1")
            if e["kind"] == "meets"]
    assert line, "the option collapses to meets, so the entry must exist"
    text = line[0]["text"]
    assert "latency_p95 on qdrant" in text, text
    assert "not true of every engine measured" in text, text
    assert "latency_p95 does not on pgvector (fails)" in text, text
    assert "qps does not on pgvector (fails)" in text, text
    assert "at least one engine measured, not on all of them" in text, text


def test_the_meets_line_is_unqualified_when_every_engine_meets():
    """The clause is a statement about the evidence, not decoration."""
    opt = _option(latency=[MEETS, MEETS], qps=[MEETS, MEETS])
    text = [e["text"] for e in rep.decision_log([opt], [], opt, CONSTRAINTS,
                                                None, env_id="pod-1")
            if e["kind"] == "meets"][0]
    assert "not true of every engine" not in text, text
    assert "latency_p95 on qdrant" in text and "latency_p95 on pgvector" in text


def test_the_meets_line_flags_a_couldnt_check_engine_too():
    """couldnt_check on one engine is also "not on all of them".

    Rounding it up -- treating an unmeasured engine as one that agreed --
    is the same move the three-outcome rule exists to prevent.
    """
    opt = _option(latency=[MEETS, CC], qps=[MEETS, MEETS])
    text = [e["text"] for e in rep.decision_log([opt], [], opt, CONSTRAINTS,
                                                None, env_id="pod-1")
            if e["kind"] == "meets"][0]
    assert "latency_p95 does not on pgvector (couldnt_check)" in text, text


# --------------------------------------------------------------------------
# the accessor that produced two of the three
# --------------------------------------------------------------------------

def test_no_module_reaches_for_the_first_verdict_of_a_constraint():
    """`verdict_for` is gone, and a guard keeps it gone.

    Two of the three defects above came from one method that returned the
    first of several verdicts. A third caller is how this comes back -- the
    same reasoning as 017b's guard against a second unquoted `export %s=%s`.

    An AST walk, not a text match: the fix's own comments name the method they
    removed, and a guard that cannot tell code from prose would have to be
    weakened or allowlisted on its first day.
    """
    root = os.path.normpath(os.path.join(HERE, "..", ".."))
    # The code that ships. `tasks/scratch/` is deliberately outside it: a
    # diagnostic script reaches into internals on purpose and is never
    # installed, and the negative control for this very guard has to name the
    # method it is restoring.
    roots = [os.path.join(root, d) for d in
             ("oneground", "adapters", "models", "policies", "corpora")]
    hits = []
    scanned = 0
    for base in roots:
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames
                           if d not in ("__pycache__", "node_modules")]
            for name in filenames:
                if not name.endswith(".py"):
                    continue
                p = os.path.join(dirpath, name)
                try:
                    with open(p, encoding="utf-8") as f:
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore")
                            tree = ast.parse(f.read())
                except (OSError, SyntaxError, UnicodeDecodeError):
                    continue
                scanned += 1
                for node in ast.walk(tree):
                    if (isinstance(node, ast.Attribute)
                            and node.attr == "verdict_for"):
                        hits.append("%s:%d" % (os.path.relpath(p, root),
                                               node.lineno))
                    if (isinstance(node, ast.FunctionDef)
                            and node.name == "verdict_for"):
                        hits.append("%s:%d" % (os.path.relpath(p, root),
                                               node.lineno))
    # An empty result only means something if the walk looked at something.
    assert scanned > 50, "the walk parsed only %d files" % scanned
    assert not hits, (
        "a single-verdict accessor is back; with two engines it hands one "
        "engine's answer back as the configuration's: %s" % hits)


def test_verdicts_for_returns_every_verdict():
    opt = _option()
    assert len(opt.verdicts_for("latency_p95")) == 2
    assert len(opt.verdicts_for("recall_at_10")) == 1
    assert opt.verdicts_for("nothing_asked_for") == []


def _main():
    """Run every test in this file without a test-runner dependency."""
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print("ok   %s" % name)
        except AssertionError as e:                       # noqa: PERF203
            failed += 1
            print("FAIL %s\n     %s" % (name, e))
    print("\n%d/%d passed" % (len(fns) - failed, len(fns)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
