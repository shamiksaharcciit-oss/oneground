"""Task 028: the tier-1 command, and what its cards may never say.

Synthetic throughout: a 2,000-vector corpus is characterized and simulated
once for the module, and every proposal here is measured on it by the real
command. The cards in the task report are the same code on the arXiv workdir.

The tests that matter most are the ones with a negative control -- the claim
invariant, the forbidden claims and the baseline citation each have a mutant
that must be caught, because a guard nobody has seen fail is a guard nobody
knows works.
"""

import ast
import json
import os
import sys

import pytest
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

from oneground import characterize, simulate                    # noqa: E402
from oneground.proposals import card as C                       # noqa: E402
from oneground.proposals import propose                         # noqa: E402
from oneground.proposals.verdict import (COULDNT_CHECK,         # noqa: E402
                                         DID_NOT_HOLD, HELD)
from oneground.report import claims as cl                       # noqa: E402
from oneground.simulate import test_simulate as ts              # noqa: E402

BASE = {"centroids": 8, "epsilon": 0.1, "probe": 1, "M": 16, "efSearch": 64}

POLICY = {"policy": {
    "family": "semantic_sharded",
    "configuration": dict(BASE),
    "changes": [{"param": "probe", "from": 1, "to": 2}],
    "rationale": "probe one more region"}}

PREDICTION = {"expects": [{"metric": "recall_at_10", "direction": "rises",
                           "by_at_least": 0.02}],
              "side_effects": [{"metric": "storage_amplification",
                                "stays_at_or_below": 4.0}]}


def _write(path, doc):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump(doc, f, sort_keys=False)
    return path


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory):
    """A characterized, simulated workdir with the baseline row in it."""
    tmp = str(tmp_path_factory.mktemp("propose"))
    vp, qp = ts._corpus(tmp)
    block = {"kind": "declared", "families": ["semantic_sharded"],
             "ground_truth_k": 20,
             "include": [dict(BASE, family="semantic_sharded")],
             "grid": {"semantic_sharded": {
                 "centroids": [8], "epsilon": [0.1], "probe": [1],
                 "M": [16], "efSearch": [64]}}}
    req = ts._req(tmp, vp, qp, block)
    ts._capture(characterize.run, req, log_fn=ts._quiet)
    ts._capture(simulate.run, req, log_fn=ts._quiet)
    return {"tmp": tmp, "req": req, "wd": os.path.join(tmp, "out"),
            "policy": _write(os.path.join(tmp, "policy.yaml"), POLICY),
            "prediction": _write(os.path.join(tmp, "prediction.yaml"),
                                 PREDICTION)}


def _propose(run_dir, name, policy=None, prediction=None, **kw):
    """Run the real command and return its card."""
    ts._capture(propose.run, run_dir["wd"], policy or run_dir["policy"],
                prediction or run_dir["prediction"], name=name,
                log_fn=ts._quiet, **kw)
    with open(os.path.join(run_dir["wd"], "proposals", name, "card.json"),
              encoding="utf-8") as f:
        return json.load(f)


def _refusal(run_dir, name="refused", policy=None, prediction=None, **kw):
    with pytest.raises(propose.ProposeError) as e:
        ts._capture(propose.run, run_dir["wd"], policy or run_dir["policy"],
                    prediction or run_dir["prediction"], name=name,
                    log_fn=ts._quiet, **kw)
    return e.value.problems


# --------------------------------------------------------------- the loop
def test_a_proposal_measures_the_change_and_writes_a_card_synthetic(run_dir):
    card = _propose(run_dir, "held")
    assert card["outcome"] == HELD, card["judgement"]
    out = os.path.join(run_dir["wd"], "proposals", "held")
    assert sorted(os.listdir(out)) == [
        "MANIFEST.sha256", "card.html", "card.json", "prediction.json",
        "propose_info.json"]


def test_the_baseline_is_not_re_run_synthetic(run_dir):
    """Step 2, asserted where it can be seen: one configuration is measured.

    The baseline row is the one `simulate` already wrote, cited by the digest
    of the file and of the row itself.
    """
    measured = []

    def spy(plan, log_fn):
        measured.append(plan.policy.to_config.label)
        return propose.measure_changed(plan, log_fn)

    card = _propose(run_dir, "one-run", measure=spy)
    assert measured == [card["configurations"]["changed"]["label"]]
    base = card["configurations"]["baseline"]
    assert base["re_run"] is False
    assert base["file"] == "simulate.json"
    assert len(base["row_sha256"]) == 64 and len(base["file_sha256"]) == 64
    info = json.load(open(os.path.join(run_dir["wd"], "proposals", "one-run",
                                       "propose_info.json"),
                          encoding="utf-8"))
    assert info["measured"] == [card["configurations"]["changed"]["label"]]
    assert info["not_measured"] == [base["label"]]


def _stub_row(label):
    """A measured row, as `measure_config` hands one back."""
    # Above the fixture's baseline by more than the predicted 0.02, so the
    # prediction holds and the outcome is the same for both shapes.
    return {"config": label, "family": "semantic_sharded",
            "params": dict(BASE, probe=2), "recall_at_1": 0.99,
            "recall_at_10": 1.0, "recall_at_100": 0.9, "ceiling_at_10": 1.0,
            "routing_loss": 0.0, "index_loss": 0.0,
            "inv_ratio_at_10": 0.99, "storage_amplification": 1.5,
            "fanout": 2.0, "est_memory_bytes": 1234567}


@pytest.mark.parametrize("shape", ["row", "row_and_timing"])
def test_a_measurement_may_be_a_row_or_a_row_and_timing_synthetic(run_dir,
                                                                  shape):
    """Both shapes, because two branches return different ones.

    `simulate.measure_config` returns the row here and `(row, timing)` after
    task 020b lands on `main`. Git merges those two changes without a
    conflict and the merged tree then failed every proposal test on a tuple
    reaching `judge()` — the release rehearsal found it. Accepting either
    shape is what makes that merge hands-off, and this is the test that says
    both work.
    """
    from oneground.proposals import validate_policy
    label = validate_policy(POLICY).to_config.label
    row, timing = _stub_row(label), {"build_seconds": 1.5,
                                     "query_seconds": 0.25}

    def measure(plan, log_fn):
        return dict(row) if shape == "row" else (dict(row), dict(timing))

    card = _propose(run_dir, "shape-" + shape, measure=measure)
    assert card["outcome"] == HELD, card["judgement"]
    assert card["measured"]["changed"]["recall_at_10"] == row["recall_at_10"]
    info = json.load(open(os.path.join(run_dir["wd"], "proposals",
                                       "shape-" + shape, "propose_info.json"),
                          encoding="utf-8"))
    assert info["timing"] == (None if shape == "row" else timing), info


def test_row_and_timing_normalises_both_shapes_synthetic():
    """The shim itself, without a run around it."""
    row = _stub_row("x")
    assert propose.row_and_timing(row) == (row, None)
    assert propose.row_and_timing((row, {"build_seconds": 1})) == (
        row, {"build_seconds": 1})


def test_the_card_carries_what_the_brief_lists_synthetic(run_dir):
    card = _propose(run_dir, "complete")
    assert card["policy"] == POLICY["policy"]                 # in full
    assert card["prediction"]["sha256"] and card["prediction"]["expects"]
    assert card["configurations"]["baseline"]["label"] != \
        card["configurations"]["changed"]["label"]
    metrics = {r["metric"] for r in card["judgement"]["rows"]}
    assert metrics == {"recall_at_10", "storage_amplification"}
    assert card["environment"]["environment_id"]
    assert card["calibration"]["tolerance"] == 0.01
    assert card["calibration"]["statements"]
    assert card["outcome"] in (HELD, DID_NOT_HOLD, COULDNT_CHECK)


def test_the_prediction_digest_is_cited_by_the_run_synthetic(run_dir):
    card = _propose(run_dir, "cited")
    path = os.path.join(run_dir["wd"], "proposals", "cited", "prediction.json")
    from oneground.receipts import sha256_file
    assert card["prediction"]["sha256"] == sha256_file(path)
    doc = json.load(open(path, encoding="utf-8"))
    assert doc["kind"] == "declared"
    assert doc["baseline"]["row_sha256"] == \
        card["configurations"]["baseline"]["row_sha256"]


# ------------------------------------------------ the side-effect budget
def test_a_breached_budget_is_did_not_hold_with_the_breach_first_synthetic(
        run_dir):
    """Step 5. The predicted metric moved as promised; the budget did not
    survive it, and that is what the card says first."""
    tight = _write(os.path.join(run_dir["tmp"], "tight.yaml"),
                   {"expects": PREDICTION["expects"],
                    "side_effects": [{"metric": "storage_amplification",
                                      "stays_at_or_below": 1.0}]})
    card = _propose(run_dir, "breach", prediction=tight)
    assert card["outcome"] == DID_NOT_HOLD
    rows = C.order_rows(card["judgement"]["rows"])
    assert rows[0]["kind"] == "side_effect"
    assert rows[0]["outcome"] == DID_NOT_HOLD
    assert [r["outcome"] for r in card["judgement"]["rows"]
            if r["kind"] == "expects"] == [HELD]
    # the headline names the breach, before any sentence about the metric
    text = card["text"]
    headline = next(t for t in text if t.startswith("The prediction"))
    assert "storage_amplification" in headline, headline
    first_row_sentence = next(t for t in text
                              if t.startswith(("Side-effect", "recall_at_10")))
    assert first_row_sentence.startswith("Side-effect"), text


def test_a_budget_row_is_judged_on_the_changed_row_not_the_delta_synthetic(
        run_dir):
    card = _propose(run_dir, "budget-value")
    row = [r for r in card["judgement"]["rows"]
           if r["kind"] == "side_effect"][0]
    assert row["value"] == card["measured"]["changed"][
        "storage_amplification"]
    assert row["bound"] == 4.0


# ------------------------------------------------------- failures are cards
def test_a_run_that_could_not_complete_still_writes_a_card_synthetic(run_dir):
    def boom(plan, log_fn):
        raise MemoryError("not enough memory to build the index")

    card = _propose(run_dir, "failed", measure=boom)
    assert card["outcome"] == COULDNT_CHECK
    assert "MemoryError" in card["failure"]
    assert [r["outcome"] for r in card["judgement"]["rows"]] == \
        [COULDNT_CHECK, COULDNT_CHECK]
    joined = " ".join(card["text"])
    assert "not enough memory" in joined
    assert "What would settle it" in joined
    assert os.path.exists(os.path.join(run_dir["wd"], "proposals", "failed",
                                       "card.html"))


def test_a_failed_run_can_be_run_again_on_the_same_prediction_synthetic(
        run_dir):
    """The remedy the couldn't-check card names has to be one that works."""
    def boom(plan, log_fn):
        raise MemoryError("not enough memory")

    first = _propose(run_dir, "retry", measure=boom)
    path = os.path.join(run_dir["wd"], "proposals", "retry", "prediction.json")
    before = open(path, "rb").read()
    second = _propose(run_dir, "retry")
    assert first["outcome"] == COULDNT_CHECK
    assert second["outcome"] == HELD
    assert open(path, "rb").read() == before, "the prediction was rewritten"
    assert second["prediction"]["sha256"] == first["prediction"]["sha256"]


# --------------------------------------------------------------- refusals
def test_a_missing_baseline_row_refuses_and_names_what_to_run_synthetic(
        run_dir):
    absent = _write(os.path.join(run_dir["tmp"], "absent.yaml"),
                    {"policy": dict(POLICY["policy"],
                                    configuration=dict(BASE, centroids=16),
                                    changes=[{"param": "probe", "from": 1,
                                              "to": 2}])})
    problems = _refusal(run_dir, policy=absent)
    text = " ".join(problems)
    assert "no baseline row for" in text
    assert "oneground simulate" in text
    assert "simulate.include" in text


def test_a_baseline_that_moved_after_the_prediction_refuses_synthetic(run_dir):
    """The digest is the point: a row that changed is not the row the
    prediction was written against, and comparing against it anyway is the
    quiet version of re-running the baseline."""
    _propose(run_dir, "moved")
    sim_path = os.path.join(run_dir["wd"], "simulate.json")
    original = open(sim_path, "rb").read()
    doc = json.loads(original)
    for row in doc["rows"]:
        if row["config"] == POLICY["policy"]["family"] + \
                "[M=16,centroids=8,efSearch=64,epsilon=0.1,probe=1]":
            row["recall_at_10"] = row["recall_at_10"] - 0.1
    with open(sim_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f)
    try:
        problems = _refusal(run_dir, name="moved")
    finally:
        with open(sim_path, "wb") as f:
            f.write(original)
    text = " ".join(problems)
    assert "the baseline moved after the prediction was written" in text
    assert "oneground simulate" in text


def test_a_different_prediction_in_the_same_directory_refuses_synthetic(
        run_dir):
    _propose(run_dir, "once")
    other = _write(os.path.join(run_dir["tmp"], "other.yaml"),
                   {"expects": [{"metric": "recall_at_10",
                                 "direction": "rises", "by_at_least": 0.5}],
                    "side_effects": []})
    problems = _refusal(run_dir, name="once", prediction=other)
    text = " ".join(problems)
    assert "pre-registers a different prediction" in text
    assert "--name" in text


def test_every_problem_is_named_at_once_synthetic(run_dir):
    """The 022 rule: one run tells you everything that is wrong."""
    bad_policy = _write(os.path.join(run_dir["tmp"], "bad-policy.yaml"),
                        {"policy": {"family": "disk_tiered",
                                    "configuration": {"probe": 1},
                                    "changes": [{"param": "probe", "from": 1,
                                                 "to": 2}],
                                    "scope": "recent_documents"}})
    bad_prediction = _write(os.path.join(run_dir["tmp"], "bad-pred.yaml"),
                            {"expects": [{"metric": "est_memory_bytes",
                                          "direction": "sideways",
                                          "by_at_least": 0.0001}]})
    problems = _refusal(run_dir, policy=bad_policy, prediction=bad_prediction)
    text = " ".join(problems)
    assert len(problems) >= 4, problems
    assert "no model family named 'disk_tiered'" in text
    assert "requires a family that does not exist" in text      # the scope
    assert "not a metric this measures" in text
    assert "is not one of rises, falls" in text
    assert "below the calibration tolerance" in text


def test_a_workdir_without_a_simulate_run_refuses_synthetic(run_dir,
                                                            tmp_path):
    empty = str(tmp_path)
    with pytest.raises(propose.ProposeError) as e:
        propose.run(empty, run_dir["policy"], run_dir["prediction"],
                    log_fn=ts._quiet)
    text = " ".join(e.value.problems)
    assert "simulate.json" in text and "oneground simulate" in text


def test_a_corpus_file_that_changed_refuses_synthetic(run_dir, tmp_path):
    """The sample the baseline row was measured on, still hashing the same."""
    import numpy as np
    vectors = os.path.join(run_dir["tmp"], "v.npy")
    original = open(vectors, "rb").read()
    v = np.load(vectors)
    v[0] = -v[0]
    np.save(vectors, v)
    try:
        problems = _refusal(run_dir, name="moved-corpus")
    finally:
        with open(vectors, "wb") as f:
            f.write(original)
    text = " ".join(problems)
    assert "is not the file the baseline row was measured on" in text
    assert "oneground characterize" in text


# ---------------------------------------------------------------- dry run
def test_dry_run_measures_nothing_and_writes_nothing_synthetic(run_dir):
    def boom(plan, log_fn):                       # never reached
        raise AssertionError("a dry run measured something")

    out, text = ts._capture(propose.run, run_dir["wd"], run_dir["policy"],
                            run_dir["prediction"], name="dry", dry_run=True,
                            log_fn=ts._quiet, measure=boom)
    assert out == 0
    assert not os.path.exists(os.path.join(run_dir["wd"], "proposals", "dry"))
    assert "nothing was measured and nothing was written" in text
    assert "would measure" in text and "baseline (not run)" in text


# ----------------------------------------------- what a card may never say
FORBIDDEN_SENTENCES = (
    "We recommend this change.",
    "This configuration is better and should be deployed.",
    "The same result will hold at full scale.",
    "It holds on any corpus like this one.",
    # Task 034. Four algorithms trade differently and the trade is the
    # finding, so ranking them is the same kind of claim as recommending a
    # configuration; and a memory figure belongs to the corpus it was
    # measured on, because a quantiser's codebook is learned from it.
    "IVF-PQ outperforms HNSW here.",
    "For this corpus, ivf is the right index.",
    "The same memory on any corpus of this size.",
)


def test_no_card_says_the_change_is_good_or_recommended_synthetic(run_dir):
    for name in ("held", "breach", "failed"):
        card = _propose(run_dir, name) if not os.path.exists(
            os.path.join(run_dir["wd"], "proposals", name)) else json.load(
                open(os.path.join(run_dir["wd"], "proposals", name,
                                  "card.json"), encoding="utf-8"))
        html = open(os.path.join(run_dir["wd"], "proposals", name,
                                 "card.html"), encoding="utf-8").read()
        assert C.card_violations(card, html) == [], name


@pytest.mark.parametrize("sentence", FORBIDDEN_SENTENCES)
def test_the_forbidden_scan_catches_each_of_them_synthetic(run_dir, sentence):
    """The negative control. A scan nobody has seen fail proves nothing."""
    card = json.load(open(os.path.join(run_dir["wd"], "proposals", "held",
                                       "card.json"), encoding="utf-8"))
    card["claims"] = list(card["claims"])
    card["claims"][1] = dict(card["claims"][1],
                             text=card["claims"][1]["text"] + " " + sentence)
    assert C.card_violations(card), sentence


def test_the_limits_sentence_may_say_what_it_rules_out_synthetic(run_dir):
    """The one exemption, and the reason for it: the caveat has to use the
    words. Everything else in the card is scanned for them."""
    card = json.load(open(os.path.join(run_dir["wd"], "proposals", "held",
                                       "card.json"), encoding="utf-8"))
    limits = C.limits_text(card)
    assert C.forbidden_in(limits), "the caveat no longer names what it rules out"
    assert C.card_violations(card) == []
    assert limits in card["text"]
    # In the card's own text, not a footnote: it is one of the sentences.
    html = open(os.path.join(run_dir["wd"], "proposals", "held", "card.html"),
                encoding="utf-8").read()
    import html as _h
    assert _h.escape(limits, quote=True) in html


# ---------------------------------------------- the quantisation caveat (034)
def test_a_quantised_configuration_carries_its_own_caveat_synthetic():
    """Beside the sample caveat, not instead of it.

    A product quantiser's codebook is learned from the vectors it trained on,
    so what it costs is a property of this corpus's distribution. The card has
    to say so, and the scan must exempt that sentence for the reason it
    exempts the sample caveat: it has to use the words it rules out.
    """
    from oneground.report import claims as cl

    assert C.quantised_in({"index": "ivf_pq"}) == ("ivf_pq",)
    assert C.quantised_in({"index": "hnsw"}, {"M": 32}) == ()

    c = cl.Claim(kind="quantisation_limits", predicate="quantisation",
                 extra={"families": ("ivf_pq",)})
    cl.render(c)
    text = c.text
    assert "ivf_pq" in text and "codebook" in text, text
    # it names what it rules out, which is why it is exempt
    assert C.forbidden_in(text), text

    card = {"claims": [{"kind": "proposal_outcome", "text": "The prediction "
                                                            "held for x."},
                       {"kind": "quantisation_limits", "text": text}]}
    assert C.card_violations(card) == []
    assert text in C.caveat_texts(card)
    assert text not in C.scannable_text(card)


def test_the_sample_is_named_in_the_cards_own_text_synthetic(run_dir):
    card = json.load(open(os.path.join(run_dir["wd"], "proposals", "held",
                                       "card.json"), encoding="utf-8"))
    limits = C.limits_text(card)
    assert "one run of one policy on one sample" in limits
    assert str(card["sample"]["n_base"]) in limits.replace(",", "")


# ------------------------------------------------------- the 019 invariant
def test_every_card_sentence_follows_from_its_rows_synthetic(run_dir):
    for name in ("held", "breach", "failed"):
        path = os.path.join(run_dir["wd"], "proposals", name, "card.json")
        card = json.load(open(path, encoding="utf-8"))
        claims = [cl.Claim.from_dict(d) for d in card["claims"]]
        rows = C.build_rows(card["judgement"], card["measured"]["baseline"],
                            card["measured"]["changed"],
                            card["configurations"]["baseline"]["label"],
                            card["configurations"]["changed"]["label"])
        assert cl.check_all(claims, rows) == [], name


def test_a_card_that_claims_an_outcome_its_rows_deny_is_caught_synthetic(
        run_dir):
    """The mutant 019 exists for: the sentence says held, the row says not."""
    card = json.load(open(os.path.join(run_dir["wd"], "proposals", "breach",
                                       "card.json"), encoding="utf-8"))
    rows = C.build_rows(card["judgement"], card["measured"]["baseline"],
                        card["measured"]["changed"],
                        card["configurations"]["baseline"]["label"],
                        card["configurations"]["changed"]["label"])
    claims = [cl.Claim.from_dict(d) for d in card["claims"]]
    budget = next(c for c in claims if c.kind == "proposal_budget")
    budget.asserts_outcome = HELD
    budget.predicate = HELD
    problems = cl.check(budget, rows)
    assert any("claims to hold for" in p for p in problems), problems


def test_a_card_that_prints_a_number_it_does_not_cite_is_caught_synthetic(
        run_dir):
    card = json.load(open(os.path.join(run_dir["wd"], "proposals", "held",
                                       "card.json"), encoding="utf-8"))
    rows = C.build_rows(card["judgement"], card["measured"]["baseline"],
                        card["measured"]["changed"],
                        card["configurations"]["baseline"]["label"],
                        card["configurations"]["changed"]["label"])
    metric = next(cl.Claim.from_dict(d) for d in card["claims"]
                  if d["kind"] == "proposal_metric")
    metric.cites = tuple(
        c if c.member != card["configurations"]["changed"]["label"]
        else cl.Cite(member=c.member, value=0.123456, source=c.source,
                     outcome=c.outcome, constraint=c.constraint)
        for c in metric.cites)
    problems = cl.check(metric, rows)
    assert any("but the row says" in p for p in problems), problems


def test_the_page_is_built_from_the_card_alone_synthetic(run_dir):
    """`card.html` is a rendering of `card.json`, so a reader who has the
    receipt can rebuild the page and see they agree."""
    path = os.path.join(run_dir["wd"], "proposals", "held")
    card = json.load(open(os.path.join(path, "card.json"), encoding="utf-8"))
    rebuilt = C.render_card_html(card)
    written = open(os.path.join(path, "card.html"), encoding="utf-8").read()
    assert rebuilt == written
    for sentence in card["text"]:
        import html as _h
        assert _h.escape(sentence, quote=True) in rebuilt


def test_a_card_carries_no_machine_identifier_synthetic(run_dir):
    """A card is published, so task 014's rule applies to it.

    `build_info.json` records the corpus paths, and on this machine they run
    through a home directory; a card names those files and their digests
    instead.
    """
    from oneground import environment as env
    for name in ("held", "breach", "failed"):
        d = os.path.join(run_dir["wd"], "proposals", name)
        blob = open(os.path.join(d, "card.json"), encoding="utf-8").read()
        page = open(os.path.join(d, "card.html"), encoding="utf-8").read()
        assert env.scan_text(blob) == [], (name, env.scan_text(blob)[:2])
        assert env.scan_text(page) == [], (name, env.scan_text(page)[:2])


def test_the_page_makes_no_network_call_synthetic(run_dir):
    html = open(os.path.join(run_dir["wd"], "proposals", "held", "card.html"),
                encoding="utf-8").read()
    for needle in ("http://", "https://", "//cdn", "<script", "@import"):
        assert needle not in html, needle


# -------------------------------------------------- no model, anywhere
NETWORK = ("requests", "urllib", "http.client", "httpx", "socket", "openai",
           "anthropic", "ollama")
MODEL_WORDS = ("api_key", "prompt", "completion", "chat(", "llm")


def _docstring_ids(tree):
    """The docstrings, which are prose about the rule and not the rule broken.

    The same reasoning as task 014's `platform.node()` guard: two modules
    there carry prose saying "not this, and here is why", and a guard that
    punished the explanation would be answered by deleting the explanation.
    This module's own docstring says "no model, no API call, no prompt".
    """
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", None) or []
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                out.add(id(body[0].value))
    return out


def _model_offences(path):
    """[(what, where)] for anything in this file that is a model's first step."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    docstrings = _docstring_ids(tree)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in NETWORK or a.name in NETWORK:
                    out.append(("imports %s" % a.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in NETWORK:
                out.append(("imports from %s" % node.module, node.lineno))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings:
                continue
            for word in MODEL_WORDS:
                if word in node.value.lower():
                    out.append(("a string saying %r" % word, node.lineno))
        elif isinstance(node, ast.Name):
            for word in MODEL_WORDS:
                if word in node.id.lower():
                    out.append(("a name %r" % node.id, node.lineno))
    return out


def test_the_proposals_package_has_no_model_no_api_call_and_no_prompt():
    """Tier 1's whole point, asserted against the source.

    Tier 1 is the loop with the model removed, and it exists to prove the
    receipt machinery before a model is near it. An HTTP import or a prompt
    string here would mean tier 2 had started without anyone deciding to.
    """
    offences = []
    for name in sorted(os.listdir(HERE)):
        if not name.endswith(".py") or name == os.path.basename(__file__):
            continue
        for what, line in _model_offences(os.path.join(HERE, name)):
            offences.append("oneground/proposals/%s:%d %s" % (name, line,
                                                              what))
    assert not offences, (
        "tier 1 has no model in it, and these would be the first step of "
        "one:\n  " + "\n  ".join(offences))


def test_that_guard_sees_a_prompt_that_is_not_a_docstring_synthetic(tmp_path):
    """The negative control: prose about the rule is allowed, a prompt is not."""
    ok = tmp_path / "prose.py"
    ok.write_text('"""No model, no api_key, no prompt anywhere."""\n'
                  "X = 1\n", encoding="utf-8")
    assert _model_offences(str(ok)) == []
    bad = tmp_path / "tier2.py"
    bad.write_text("import httpx\n"
                   'PROMPT = "You are a retrieval engineer. Answer with"\n',
                   encoding="utf-8")
    found = " ".join(w for w, _ in _model_offences(str(bad))).lower()
    assert "httpx" in found and "prompt" in found, found


def test_the_command_is_guarded_like_every_other_writer():
    from oneground import cli, environment as env
    assert "oneground propose" in env.GUARDED_COMMANDS
    assert env.is_guarded(cli._cmd_propose)
    assert "oneground propose" in cli.dispatchable_commands()
