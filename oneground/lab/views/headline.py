"""A run opens on its finding, not on its files (task 041, steps 4 and 6).

The landing page for one run leads with what the report concluded and the
number that decided it. The file list is navigation; the finding is the
product. A reader who lands on a directory listing has to be taught what to
look for; a reader who lands on *nothing is recommended, because the storage
budget broke* has already understood the tool.

**The UI never writes the headline.** It is the report's own `recommendation`
claim, verbatim. For a Tier-2 report, which has no claims, it is
`recommendation_reason`, also verbatim.

THE DECIDING ROW IS RECORDED, OR THERE ISN'T ONE
------------------------------------------------
When a report recommends something, its recommendation claim cites the row:
`simulate.json:rows[LABEL]`, with the config as `member`. That citation is the
deciding row and the drawer opens from it like any other.

When a report recommends nothing, the claim's source is `(rule)` -- the
conclusion follows from a rule, not from a measurement -- and **there is no
deciding row to show**. Nothing in the report records which option came
closest, and picking one would be the UI ranking options, which is a
measurement and not a drawing. So the page says the conclusion rests on a
rule and shows the counts instead. That is less satisfying than the brief's
mock-up and it is what the receipts support.

EQUAL WEIGHT IS A PROPERTY OF THE DATA, NOT ONLY OF THE STYLING
---------------------------------------------------------------
`counts` is always all three outcomes, in a fixed order, always present, and
with nothing in the structure marking one as lesser than another -- no
"primary", no optional key, no omission at zero. A renderer cannot give
couldn't-check a muted treatment by accident if the data never hands it a
reason to. `0 couldn't check` is a count; leaving it out is a different
statement, and the easiest one to make while writing a headline.
"""

from ..contract import Drawing, Mark
from ..receipt import ReceiptView, gap

#: The three outcomes, in the one order they are ever shown.
OUTCOMES = ("meets", "fails", "couldnt_check")

#: What a Tier-1 `summary` calls each of them.
SUMMARY_KEYS = {"meets": "meets", "fails": "fails",
                "couldnt_check": "couldnt_check"}

RULE_SOURCE = "(rule)"


def _counts_from(summary=None, outcomes=None):
    """All three, always, or None when the report records none of them.

    Never partial and never zero-filled from nothing: a report that records
    two of the three is one this refuses to summarise, because a count nobody
    wrote rendered as 0 is a measurement nobody made.
    """
    if summary is not None:
        got = {k: summary.get(src) for k, src in SUMMARY_KEYS.items()}
        if any(v is None for v in got.values()):
            return None
        return [{"outcome": k, "n": int(got[k])} for k in OUTCOMES]
    if outcomes is not None:
        return [{"outcome": k, "n": sum(1 for o in outcomes if o == k)}
                for k in OUTCOMES]
    return None


class RunHeadlineView(ReceiptView):
    """What one run concluded, from its own report."""

    name = "run_headline"
    receipt = "report.json"
    reads = (
        "run",
        "tier",
        "kind",
        "recommendation",
        "recommended",
        "recommendation_reason",
        "summary",
        "constraints[].outcome",
        "claims[].kind",
        "claims[].text",
        "claims[].source",
        "claims[].cites[].source",
        "claims[].cites[].member",
        "claims[].cites[].value",
        "claims[].cites[].constraint",
    )

    def render(self, f):
        tier = f["tier"] if f.has("tier") else (2 if f.has("kind") else 1)
        headline, source, deciding = None, None, []

        if f.has_each("claims"):
            for claim in f.each("claims"):
                if claim["kind"] != "recommendation":
                    continue
                headline = claim["text"]
                source = claim["source"]
                for cite in claim.each("cites"):
                    deciding.append({
                        "source": cite["source"],
                        "member": cite["member"],
                        "value": cite["value"],
                        "constraint": cite["constraint"],
                    })
                break
        elif f.has("recommendation_reason"):
            # Tier 2 states its conclusion as a field rather than as a claim.
            headline = f["recommendation_reason"]
            source = "report.json:recommendation_reason"

        counts = None
        if f.has("summary"):
            counts = _counts_from(summary=f["summary"])
        elif f.has_each("constraints"):
            counts = _counts_from(
                outcomes=[c["outcome"] for c in f.each("constraints")])

        recommended = None
        for key in ("recommendation", "recommended"):
            if f.has(key) and f[key] is not None:
                recommended = f[key]
                break

        marks = []
        if counts is not None:
            marks.append(Mark(
                kind="row",
                data={"outcome": [c["outcome"] for c in counts],
                      "n": [c["n"] for c in counts]},
                encoding={"label": "outcome"}))
        if deciding:
            marks.append(Mark(
                kind="row",
                data={"source": [d["source"] for d in deciding],
                      "member": [d["member"] for d in deciding],
                      "value": [d["value"] for d in deciding],
                      "constraint": [d["constraint"] for d in deciding]},
                encoding={"label": "source"}))

        figures = {
            "run": f["run"] if f.has("run") else None,
            "tier": tier,
            "recommended": recommended,
            "headline": headline,
            "headline_source": source,
            # The three, always, in one order, with nothing marking one as
            # lesser. A renderer that wants to mute couldnt_check has to
            # decide to; the data will not help it.
            "outcome_order": list(OUTCOMES),
            # True when the conclusion rests on a rule rather than on a row,
            # which is a fact about the report and not a missing feature.
            "from_rule": source == RULE_SOURCE,
        }
        if counts is not None:
            figures["counts"] = counts
        if deciding:
            # A figure or a gap, never both: the contract's rule, and it is
            # right. "0 deciding rows" is the absence, and the absence has a
            # reason worth stating rather than a count worth printing.
            figures["deciding_rows"] = len(deciding)
        gaps = {}
        if headline is None:
            gaps["headline"] = gap(
                "this report records no recommendation claim and no "
                "recommendation_reason, so it states no conclusion the page "
                "could lead with")
        if counts is None:
            gaps["counts"] = gap(
                "this report records no outcome counts; showing zeros would "
                "state that every constraint was checked and none held")
        if not deciding:
            # Every absence gets its reason. Leaving one unexplained because
            # its cause seemed obvious is how a couldn't-check turns into a
            # blank space on a page.
            if source == RULE_SOURCE:
                why = ("the conclusion follows from a rule, not from a row: "
                       "nothing in the report records which option came "
                       "closest, and choosing one would be the page ranking "
                       "options rather than drawing them")
            elif tier == 2:
                why = ("a Tier-2 run measured nothing on this corpus, so "
                       "there is no row for a conclusion to rest on -- which "
                       "is the conclusion")
            else:
                why = ("this report's conclusion cites no row")
            gaps["deciding_rows"] = gap(why)
        return Drawing(view=self.name, marks=marks, figures=figures,
                       gaps=gaps,
                       caption=(headline or "this run states no conclusion"))


class RunProgressView(ReceiptView):
    """How far a run got, for a run with no report (step 4's second half).

    Drawn from the run index rather than from a receipt, because the fact
    being shown -- which stages ran -- is which receipts exist, and that is
    not written inside any one of them.

    It leads with the furthest stage reached and what would take it further.
    The next command is named, not invented: it is the stage that follows the
    last one that ran, in the fixed order the stages have.
    """

    name = "run_progress"
    receipt = "run_index"
    reads = ("directory_shown", "runs[].name", "runs[].stages",
             "runs[].problems")

    #: The stages in order, with the command that runs each. Naming the next
    #: command is not a suggestion: it is the stage after the last one that
    #: ran, and there is only one.
    ORDER = (("characterize", "oneground characterize <requirements.yaml>"),
             ("simulate", "oneground simulate <requirements.yaml>"),
             ("verify", "oneground verify <requirements.yaml>"),
             ("report", "oneground report <requirements.yaml>"))

    def __init__(self, run=None):
        self.run = run

    def params(self):
        return {"run": self.run}

    def render(self, f):
        wanted = self.run
        found = None
        for row in f.each("runs"):
            if row["name"] == wanted:
                found = {"name": row["name"], "stages": row["stages"],
                         "problems": list(row["problems"])}
                break

        if found is None:
            return Drawing(
                view=self.name, marks=[],
                figures={"directory": f["directory_shown"]},
                gaps={"run": gap(f"no run named {wanted!r} under "
                                 f"{f['directory_shown']}")})

        names = [s for s, _ in self.ORDER]
        ran = [s for s in names if found["stages"].get(s)]
        furthest = ran[-1] if ran else None
        nxt = next(((s, cmd) for s, cmd in self.ORDER
                    if not found["stages"].get(s)), None)

        figures = {
            "run": found["name"],
            "stages_run": ran,
            "furthest_stage": furthest,
            "next_stage": nxt[0] if nxt else None,
            "next_command": nxt[1] if nxt else None,
            "problems": found["problems"],
        }
        gaps = {"report": gap(
            "this run has not reported, so it states no conclusion; "
            + (f"the next stage is `{nxt[1]}`" if nxt
               else "every stage has run"))}
        return Drawing(
            view=self.name,
            marks=[Mark(kind="row",
                        data={"stage": names,
                              "ran": [s in ran for s in names]},
                        encoding={"label": "stage"})],
            figures=figures, gaps=gaps,
            caption=(f"reached {furthest}" if furthest
                     else "no stage has run for this workdir"))
