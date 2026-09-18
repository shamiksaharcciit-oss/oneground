"""The card: what a proposal measured, and what it may not say.

Task 028, tier 1. A card is built from rows and rendered through the 019
`Claim` renderer, so every sentence in it is reconstructible from the values
it cites and `claims.check` can go and read them. Nothing here formats an
outcome or a measured value into a string; `report/claims.py` does that, and
`report/test_claims.py`'s grep-guard covers this module.

WHAT A CARD CARRIES
    the policy in full, the prediction with its digest, the baseline and the
    changed configuration, the measured result per predicted metric, the
    side-effect budget against its bounds, the environment, the calibration
    line the verdicts were judged under, and one outcome.

WHAT A CARD MAY NEVER SAY
    that the change is good, recommended, or should be deployed; anything
    about a corpus other than the one it ran on; that a result on this sample
    holds at full scale. `FORBIDDEN` is that rule, executable: `forbidden_in`
    scans every rendered sentence and the page built from them.

    The limits sentence is exempt, and only that one. It has to name the
    boundaries it is drawing -- other corpora, the corpus this sample came
    from -- and a scanner that punished it would teach the next person to
    delete the caveat rather than the claim. It is a constant, rendered from
    `proposal_limits` and asserted verbatim by its own test, so exempting it
    exempts nothing that could drift.

THE BREACH COMES FIRST
    A proposal whose predicted metric moved as promised but whose budget was
    breached did not hold, and the card says so before it says anything about
    the metric that behaved. `order_rows` is that ordering, and it is the
    reason the side-effect budget is a first-class row rather than a footnote:
    most well-meaning changes die here.
"""

import html as _html
import os

from ..report import claims as cl
from .verdict import COULDNT_CHECK, DID_NOT_HOLD, HELD

CARD_NAME = "card.json"
CARD_HTML = "card.html"

# The phrases a card may never contain, lower-cased. Each is a way of saying
# one of the three forbidden things.
FORBIDDEN = (
    # that the change is good, recommended, or should be deployed
    "recommend",
    "we suggest",
    "you should",
    "should be deployed",
    "deploy this",
    "worth deploying",
    "is better",
    "is an improvement",
    "is good",
    "a good change",
    "the best",
    # anything about a corpus other than this one
    "on any corpus",
    "on other corpora",
    "corpora like yours",
    "in general",
    "generalises",
    "generalizes",
    # that a result on this sample holds at full scale
    "at full scale",
    "at production scale",
    "on the full corpus",
    "will hold at",
    "scales to",
)

# The sentences that report one judged row each.
ROW_KINDS = ("proposal_metric", "proposal_budget", "proposal_unchecked")


def _n(v, nd=4):
    """A measured number, printed the one way this module prints them."""
    return "%.*f" % (nd, float(v))


def _thousands(n):
    return "{:,}".format(int(n))


def order_rows(rows):
    """Judged rows with a breached budget first. Step 5's ordering.

    A card whose first line is the recall that rose, when the storage budget
    it promised not to break was broken, is a card that buries the finding.
    Nothing breached: the predicted change is read first and the budget it
    stayed inside after it, which is the order they were written in.
    """
    def rank(r):
        breached = r.get("outcome") == DID_NOT_HOLD
        budget = r.get("kind") == "side_effect"
        if breached:
            return (0 if budget else 1, 0)
        return (2, 1 if budget else 0)
    return sorted(rows, key=rank)


def _fact(value, outcome, source):
    return {"value": value, "outcome": outcome, "source": source}


def build_rows(judgement, baseline_row, changed_row, from_label, to_label):
    """The per-member facts every claim in the card is checked against.

    `{member: {constraint: fact}}` under the run-level key, with the changed
    configuration carrying each metric's judged outcome and the baseline
    carrying the value it was measured at. This is what makes a card's
    sentence checkable rather than merely consistent.
    """
    rows = cl.RowIndex()
    here = rows.setdefault(None, {})
    here.setdefault(to_label, {})
    here.setdefault(from_label, {})
    src_changed = "%s:measured.changed" % CARD_NAME
    src_baseline = "simulate.json:rows[%s]" % from_label
    for name, value in (changed_row or {}).items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            here[to_label][name] = _fact(value, None,
                                         "%s.%s" % (src_changed, name))
    for name, value in (baseline_row or {}).items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            here[from_label][name] = _fact(value, None,
                                           "%s.%s" % (src_baseline, name))
    for r in judgement["rows"]:
        metric = r["metric"]
        fact = here[to_label].get(metric)
        source = fact["source"] if fact else "%s.%s" % (src_changed, metric)
        value = fact["value"] if fact else None
        here[to_label][metric] = _fact(value, r["outcome"], source)
    here[to_label]["prediction"] = _fact(
        None, judgement["outcome"], "%s:outcome" % CARD_NAME)
    return rows


def build_claims(card, judgement, from_label, to_label):
    """Every sentence in the card, as a Claim, rendered."""
    sample = card["sample"]
    tolerance = card["prediction"]["calibration_tolerance"]
    common = {"n_base": _thousands(sample["n_base"]),
              "n_queries": _thousands(sample["n_queries"]),
              "run": card["run"]}
    out = []

    changes = "; ".join(
        "%s %s from %s to %s" % (card["policy"]["family"], c["param"],
                                 c["from"], c["to"])
        for c in card["policy"]["changes"])
    out.append(cl.Claim(
        kind="proposal_change", predicate="measured", subject=to_label,
        scope=(to_label,), holds_for=(to_label,),
        cites=(cl.Cite(member=to_label, source="%s:configurations.changed"
                                               % CARD_NAME),),
        extra=dict(common, changes=changes, seed=sample["seed"])))

    out.append(cl.Claim(
        kind="proposal_outcome", predicate=judgement["outcome"],
        subject=to_label, constraint="prediction",
        scope=(to_label,), holds_for=(to_label,),
        asserts_outcome=judgement["outcome"],
        cites=(cl.Cite(member=to_label, outcome=judgement["outcome"],
                       source="%s:outcome" % CARD_NAME),),
        detail=_headline_detail(judgement)))

    for r in order_rows(judgement["rows"]):
        metric = r["metric"]
        if r.get("outcome") == COULDNT_CHECK and "before" not in r \
                and "value" not in r:
            out.append(_unchecked_claim(r, to_label, tolerance))
            continue
        if r["kind"] == "expects":
            out.append(_metric_claim(card, r, from_label, to_label, tolerance))
        else:
            out.append(_budget_claim(card, r, to_label, tolerance))

    base = card["configurations"]["baseline"]
    out.append(cl.Claim(
        kind="proposal_baseline", predicate="not_re_run", subject=from_label,
        scope=(from_label,), holds_for=(from_label,),
        cites=(cl.Cite(member=from_label, source=base["source"]),),
        extra={"file": base["file"], "file_sha256": base["file_sha256"][:12],
               "row_sha256": base["row_sha256"][:12],
               "measured_at": base["measured_at"]}))

    out.append(cl.Claim(
        kind="proposal_calibration", predicate="tolerance",
        detail=" ".join(card["calibration"]["statements"]),
        extra={"tolerance": tolerance,
               "literal_numbers": (str(tolerance),)}))

    out.append(cl.Claim(kind="proposal_limits", predicate="limits",
                        extra=dict(common)))

    for c in out:
        cl.render(c)
    return out


def _headline_detail(judgement):
    """The judge's own words for why, breach first. A quotation, not a claim."""
    if judgement.get("reason"):
        return judgement["reason"]
    ordered = order_rows(judgement["rows"])
    if ordered and ordered[0]["outcome"] != HELD:
        return ordered[0].get("detail", "")
    return ""


def _literals(*values):
    return tuple(str(v) for v in values)


def _metric_claim(card, r, from_label, to_label, tolerance):
    predicted = _predicted(card, r["metric"], "expects")
    return cl.Claim(
        kind="proposal_metric", predicate=r["outcome"], subject=to_label,
        constraint=r["metric"], scope=(to_label,),
        holds_for=(to_label,), asserts_outcome=r["outcome"],
        cites=(cl.Cite(member=to_label, value=r.get("after"),
                       outcome=r["outcome"],
                       source="%s:measured.changed.%s" % (CARD_NAME,
                                                          r["metric"])),
               cl.Cite(member=from_label, value=r.get("before"),
                       source="simulate.json:rows[%s].%s" % (from_label,
                                                             r["metric"]),
                       constraint=r["metric"])),
        detail=r.get("detail", ""),
        extra={"direction": predicted.get("direction"),
               "delta": _n(r.get("delta", 0)),
               "before": _n(r.get("before", 0)),
               "after": _n(r.get("after", 0)),
               "threshold": predicted.get("by_at_least"),
               "literal_numbers": _literals(predicted.get("by_at_least"),
                                            tolerance)})


def _budget_claim(card, r, to_label, tolerance):
    predicted = _predicted(card, r["metric"], "side_effects")
    bound_key = [k for k in predicted if k != "metric"]
    phrase = ("at most" if bound_key and bound_key[0] == "stays_at_or_below"
              else "at least")
    return cl.Claim(
        kind="proposal_budget", predicate=r["outcome"], subject=to_label,
        constraint=r["metric"], scope=(to_label,),
        holds_for=(to_label,), asserts_outcome=r["outcome"],
        cites=(cl.Cite(member=to_label, value=r.get("value"),
                       outcome=r["outcome"],
                       source="%s:measured.changed.%s" % (CARD_NAME,
                                                          r["metric"])),),
        detail=r.get("detail", ""),
        extra={"after": _n(r.get("value", 0)), "bound_phrase": phrase,
               "bound": r.get("bound"),
               "literal_numbers": _literals(r.get("bound"), tolerance)})


def _unchecked_claim(r, to_label, tolerance):
    """A row with no numbers: the run did not produce them."""
    return cl.Claim(
        kind="proposal_unchecked", predicate=COULDNT_CHECK, subject=to_label,
        constraint=r["metric"], scope=(to_label,), holds_for=(to_label,),
        asserts_outcome=COULDNT_CHECK,
        cites=(cl.Cite(member=to_label, outcome=COULDNT_CHECK,
                       source="%s:measured.changed.%s" % (CARD_NAME,
                                                          r["metric"])),),
        detail=r.get("detail", ""),
        extra={"literal_numbers": _literals(tolerance)})


def _predicted(card, metric, where):
    for e in card["prediction"].get(where) or ():
        if e["metric"] == metric:
            return e
    return {}


# --------------------------------------------------------------------------
# the forbidden claims
# --------------------------------------------------------------------------

def scannable_text(card):
    """Every sentence a card asserts, minus the limits sentence.

    See the module docstring: the caveat names the boundaries it draws, so
    scanning it for the words it must use is a rule that deletes caveats.
    """
    return [c["text"] for c in card.get("claims") or ()
            if c.get("kind") != "proposal_limits"]


def limits_text(card):
    for c in card.get("claims") or ():
        if c.get("kind") == "proposal_limits":
            return c["text"]
    return ""


def forbidden_in(text):
    """Every forbidden phrase in one string, lower-cased."""
    low = " ".join(str(text).lower().split())
    return tuple(p for p in FORBIDDEN if p in low)


def card_violations(card, html=""):
    """Every forbidden phrase in a card's sentences and in its page."""
    bad = []
    for sentence in scannable_text(card):
        for phrase in forbidden_in(sentence):
            bad.append("card sentence says %r: %s" % (phrase, sentence[:120]))
    if html:
        page = html
        caveat = limits_text(card)
        if caveat:
            page = page.replace(_html.escape(caveat, quote=True), " ")
            page = page.replace(caveat, " ")
        for phrase in forbidden_in(page):
            bad.append("card.html says %r" % phrase)
    return bad


# --------------------------------------------------------------------------
# the page
# --------------------------------------------------------------------------

TOKENS_CSS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "..", "docs", "design", "tokens.css")

OUTCOME_TOKEN = {HELD: "teal", DID_NOT_HOLD: "coral", COULDNT_CHECK: "amber"}


def _css():
    try:
        with open(TOKENS_CSS, encoding="utf-8") as f:
            return f.read()
    except OSError:                                   # pragma: no cover
        return (":root{--slate:#1B2432;--panel:#243040;--ink:#E7EAEF;"
                "--muted:#8B96A5;--ochre:#C99A3B;--teal:#4FC1AD;"
                "--coral:#E36C5E;--amber:#D9A441;"
                "--font-ui:system-ui,sans-serif;--font-mono:monospace;}")


def esc(x):
    return _html.escape("" if x is None else str(x), quote=True)


def _rows_table(card):
    out = ["<table><thead><tr><th>metric</th><th>kind</th>"
           "<th>baseline</th><th>changed</th><th>predicted</th>"
           "<th>outcome</th></tr></thead><tbody>"]
    for r in order_rows(card["judgement"]["rows"]):
        predicted = _predicted(card, r["metric"],
                               "expects" if r["kind"] == "expects"
                               else "side_effects")
        want = ", ".join("%s %s" % (k, v) for k, v in predicted.items()
                         if k != "metric")
        before = r.get("before")
        after = r.get("after", r.get("value"))
        out.append(
            "<tr><td><code>%s</code></td><td class='kind'>%s</td>"
            "<td class='num'>%s</td><td class='num'>%s</td>"
            "<td class='muted'>%s</td><td class='v %s'>%s</td></tr>"
            % (esc(r["metric"]), esc(r["kind"].replace("_", " ")),
               esc("" if before is None else _n(before)),
               esc("" if after is None else _n(after)),
               esc(want),
               esc(OUTCOME_TOKEN.get(r["outcome"], "muted")),
               esc(cl.outcome_label(r["outcome"]))))
    out.append("</tbody></table>")
    return "\n".join(out)


def _sentences(card, kinds):
    return "\n".join(
        "<p%s>%s</p>" % (" class='note'" if kind != "proposal_outcome" else "",
                         esc(c["text"]))
        for c in card.get("claims") or ()
        for kind in (c.get("kind"),) if kind in kinds)


def render_card_html(card):
    """The card as one self-contained page, from `card.json` alone.

    No network calls of any kind, for the reason `report/html.py` gives.
    """
    outcome = card["outcome"]
    token = OUTCOME_TOKEN.get(outcome, "amber")
    policy = card["policy"]
    pred = card["prediction"]
    return """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>oneground proposal card -- %(run)s</title>
<style>
%(css)s
*{box-sizing:border-box}
body{margin:0;background:var(--slate);color:var(--ink);
  font-family:var(--font-ui);line-height:1.55;font-size:15px}
.wrap{max-width:900px;margin:0 auto;padding:48px 28px 96px}
code,.digest{font-family:var(--font-mono);font-size:.86em}
h1{font-size:1.5rem;margin:.2em 0 .5em;font-weight:600}
h2{font-size:1rem;margin:2.4rem 0 .4rem;font-weight:600}
.masthead{display:flex;justify-content:space-between;align-items:baseline;
  border-bottom:1px solid #33405422;padding-bottom:14px;margin-bottom:34px}
.masthead .name{color:var(--ochre);font-weight:600;letter-spacing:.02em}
.masthead .env{color:var(--muted);font-size:.85rem}
.verdict{background:var(--panel);border-radius:10px;padding:22px 26px;
  border-left:3px solid var(--%(token)s)}
.verdict p{margin:.3rem 0}
.label{text-transform:uppercase;letter-spacing:.14em;font-size:.68rem;
  color:var(--muted)}
.note{color:var(--muted);max-width:74ch;font-size:.9rem}
table{width:100%%;border-collapse:collapse;font-size:.84rem;margin-top:.6rem}
th{text-align:left;font-weight:500;color:var(--muted);padding:8px 10px;
  border-bottom:1px solid #33405433;font-size:.76rem;
  text-transform:uppercase;letter-spacing:.07em}
td{padding:9px 10px;border-bottom:1px solid #2b374a55;vertical-align:top}
.num{text-align:right;font-family:var(--font-mono);font-size:.8rem}
.teal{color:var(--teal)} .coral{color:var(--coral)} .amber{color:var(--amber)}
.muted,.kind{color:var(--muted)}
pre{background:#1f2836;border-radius:8px;padding:14px 16px;overflow-x:auto;
  font-family:var(--font-mono);font-size:.78rem;color:var(--ink)}
.digests{color:var(--muted);font-size:.72rem;word-break:break-all}
</style></head>
<body><div class="wrap">
<div class="masthead"><span class="name">oneground &middot; proposal card</span>
<span class="env">%(env)s</span></div>
<h1>%(run)s</h1>

<div class="verdict">
<p class="label">outcome</p>
%(headline)s
</div>

<h2>What was measured</h2>
%(change)s

<h2>The prediction, and what happened</h2>
%(table)s
%(rows)s

<h2>The policy, in full</h2>
<pre>%(policy)s</pre>

<h2>The prediction, as written</h2>
<pre>%(prediction)s</pre>

<h2>Receipts</h2>
%(baseline)s
%(calibration)s
<p class="digests">prediction.json %(pred_sha)s &middot; policy %(policy_sha)s
&middot; cited by this run: %(cited)s</p>

<h2>Limits</h2>
%(limits)s
</div></body></html>
""" % {
        "css": _css(),
        "run": esc(card["run"]),
        "token": token,
        "env": esc(card["environment"].get("environment_id")),
        "headline": _sentences(card, ("proposal_outcome",)),
        "change": _sentences(card, ("proposal_change",)),
        "table": _rows_table(card),
        "rows": _sentences(card, ROW_KINDS),
        "policy": esc(_yaml_ish({"policy": policy})),
        "prediction": esc(_yaml_ish({"expects": pred["expects"],
                                     "side_effects": pred["side_effects"]})),
        "baseline": _sentences(card, ("proposal_baseline",)),
        "calibration": _sentences(card, ("proposal_calibration",)),
        "pred_sha": esc(pred["sha256"]),
        "policy_sha": esc(card["policy_sha256"]),
        "cited": esc(pred["cited_by_run"]),
        "limits": _sentences(card, ("proposal_limits",)),
    }


def _yaml_ish(obj, indent=0):
    """The policy and the prediction, printed as the file the user wrote.

    Not `yaml.dump`: the card shows these as the two files they are, in the
    order the documents declare them, and a dumper would sort and requote.
    """
    pad = " " * indent
    if isinstance(obj, dict):
        lines = []
        for k, v in obj.items():
            if isinstance(v, (dict, list)) and v:
                lines.append("%s%s:" % (pad, k))
                lines.append(_yaml_ish(v, indent + 2))
            else:
                lines.append("%s%s: %s" % (pad, k, _scalar(v)))
        return "\n".join(lines)
    if isinstance(obj, list):
        lines = []
        for item in obj:
            if isinstance(item, dict):
                inner = _yaml_ish(item, indent + 2).lstrip()
                lines.append("%s- %s" % (pad, inner.replace("\n", "\n" + pad
                                                            + "  ")))
            else:
                lines.append("%s- %s" % (pad, _scalar(item)))
        return "\n".join(lines)
    return "%s%s" % (pad, _scalar(obj))


def _scalar(v):
    if isinstance(v, str) and (v == "" or " " in v):
        return '"%s"' % v
    if isinstance(v, dict):
        return "{%s}" % ", ".join("%s: %s" % (k, _scalar(x))
                                  for k, x in v.items())
    return str(v)
