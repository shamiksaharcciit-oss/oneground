"""Two runs, side by side only if they may be (task 041, step 7).

The verdict is `oneground.comparability`, which `docs/LIBRARY.md` §2.2
specifies. This view draws it; it does not re-derive it.

THE NO-ALIGNMENT RULE IS STRUCTURAL, NOT STYLISTIC
---------------------------------------------------
The brief says a not-comparable pair "renders as two observations with a
divider and the reason; the page must not let a reader's eye line up two
numbers the verdict says are not comparable."

A rule enforced only by layout is a rule one stylesheet away from being lost.
So it is enforced in the drawing: **a paired mark exists only when the
verdict is `comparable`.** Otherwise each run gets its own mark, with its own
name, and there is no row in the data that holds both runs' numbers. A
renderer cannot align them into a comparison table because it is never handed
one; to break the rule it would have to join two marks itself, which is a
decision somebody has to make on purpose.

This is the same move as equal weight in the headline view. Layout drifts;
structure does not.

WHAT THIS PAGE WILL SAY TODAY
------------------------------
`couldnt_check`, on the code, for every pair — including two copies of the
same run. No artifact on this machine records the `oneground` version that
measured it, so `code` is unknown, and a missing version is never read as a
match. That is not a limitation of this view. It is §2.2's own prediction,
now measurable.
"""

from ..contract import Drawing, Mark
from ..receipt import COMPARISON, ReceiptView, gap

COMPARABLE = "comparable"
NOT_COMPARABLE = "not_comparable"
COULDNT_CHECK = "couldnt_check"

#: What a reader is told to do about each verdict. The sentence is about what
#: the page will and will not show, not advice about their runs.
WHAT_IT_MEANS = {
    COMPARABLE: "these runs may be read against each other: every "
                "ingredient that decides comparability is recorded on both "
                "and agrees",
    NOT_COMPARABLE: "these are two observations, not a comparison. A "
                    "difference between their numbers is not attributable "
                    "to the thing you are comparing",
    COULDNT_CHECK: "these are two observations. Whether they may be read "
                   "against each other is not knowable from what they "
                   "record, and an unknown is not a match",
}


class ComparisonView(ReceiptView):
    name = "comparison"
    receipt = COMPARISON
    reads = (
        "verdict",
        "reason",
        "findings[].ingredient",
        "findings[].state",
        "findings[].required",
        "findings[].left",
        "findings[].right",
        "findings[].note",
        "runs[].name",
        "runs[].n_base",
        "runs[].stages",
        "runs[].report.tier",
        "runs[].report.headline",
        "runs[].report.summary",
        "runs[].report.outcomes",
        "runs[].manifest.all_verified",
    )

    def render(self, f):
        verdict = f["verdict"]
        reason = f["reason"]

        ing, state, required, left, right, notes = [], [], [], [], [], []
        for x in f.each("findings"):
            ing.append(x["ingredient"])
            state.append(x["state"])
            required.append(x["required"])
            left.append(x["left"])
            right.append(x["right"])
            notes.append(x["note"])

        observations = []
        for row in f.each("runs"):
            tier = row["report.tier"] if row.has("report.tier") else None
            summary = (row["report.summary"]
                       if row.has("report.summary") else None)
            outcomes = (row["report.outcomes"]
                        if row.has("report.outcomes") else None)
            observations.append({
                "name": row["name"],
                "n_base": row["n_base"] if row.has("n_base") else None,
                "stages": [s for s, on in row["stages"].items() if on],
                "tier": tier,
                "headline": (row["report.headline"]
                             if row.has("report.headline") else None),
                "summary": summary,
                "outcomes": outcomes,
                "verified": row["manifest.all_verified"],
            })

        # The verdict's own row, always drawn, so the page leads with it.
        marks = [Mark(kind="row",
                      data={"ingredient": ing, "state": state,
                            "required": required, "left": left,
                            "right": right, "note": notes},
                      encoding={"label": "ingredient"})]

        if verdict == COMPARABLE:
            # Only here do the two runs share rows. One mark, both runs'
            # values in it, which is what a comparison is.
            marks.append(Mark(
                kind="row",
                data={"field": ["run", "n_base", "tier"],
                      "left": [observations[0]["name"],
                               observations[0]["n_base"],
                               observations[0]["tier"]],
                      "right": [observations[1]["name"],
                                observations[1]["n_base"],
                                observations[1]["tier"]]},
                encoding={"label": "field"}))
        else:
            # Two marks, one per run, with nothing joining them. A renderer is
            # never handed a row containing both runs' numbers.
            for obs in observations:
                marks.append(Mark(
                    kind="row",
                    data={"run": [obs["name"]],
                          "n_base": [obs["n_base"]],
                          "tier": [obs["tier"]],
                          "headline": [obs["headline"]],
                          "stages": [obs["stages"]],
                          "verified": [obs["verified"]]},
                    encoding={"label": "run"}))

        figures = {
            "verdict": verdict,
            "reason": reason,
            "means": WHAT_IT_MEANS.get(verdict),
            "runs": [o["name"] for o in observations],
            "paired": verdict == COMPARABLE,
            "differing": [i for i, s in zip(ing, state) if s == "differs"],
            "unknown": [i for i, s, r in zip(ing, state, required)
                        if s == "unknown" and r],
        }
        gaps = {}
        if verdict != COMPARABLE:
            # The absence of a comparison is itself the finding, with its
            # reason, rather than a page that quietly shows two tables.
            gaps["comparison"] = gap(
                f"{reason}. These are shown as two observations, kept apart, "
                "because a page that lines up two numbers the verdict will "
                "not vouch for has made the comparison on the reader's "
                "behalf")
        return Drawing(view=self.name, marks=marks, figures=figures,
                       gaps=gaps,
                       caption=f"{verdict}: {WHAT_IT_MEANS.get(verdict, '')}")
