"""The run list: every workdir under the runs directory (task 041, step 3).

A view over `runs.index_runs`'s document, which is transport's index and the
one drawable thing that is not a digest-checked file. Every value in it was
copied from a named receipt without recomputation, and each row carries that
run's own digest verification, so this view can say which rows are trustworthy
without checking anything itself.

**This view does the counting.** The index deliberately does not: it carries a
Tier-2 report's six `couldnt_check` outcomes across as a list and leaves them
uncounted, because counting recorded outcomes is drawing a measurement, and a
number on the page has to have come from a view.

Two report kinds reach one table. A Tier-1 report counted its own outcomes
into `summary`; a Tier-2 report has no summary and no options, and every one
of its constraints is `couldnt_check` by construction. Both become the same
three counts, and **all three are always shown, including zeros** -- `1 meets
· 6 fails · 0 couldn't check` is a different statement from `1 meets · 6
fails`, and the second invites a reader to forget the third exists.
"""

from ..contract import Drawing, Mark
from ..receipt import RUN_INDEX, ReceiptView, gap

#: The three outcomes, in the order they are always shown.
OUTCOMES = ("meets", "fails", "couldnt_check")

#: What `summary` calls them in a Tier-1 report.
SUMMARY_KEYS = {"meets": "meets", "fails": "fails",
                "couldnt_check": "couldnt_check"}

STAGES = ("characterize", "simulate", "verify", "report")


def _counts(report):
    """The three counts for one run, or None when it has no report.

    Never partial: a report that records two of the three is a report this
    function refuses to summarise, because a missing count rendered as zero
    would be a measurement nobody made.
    """
    if not report:
        return None
    summary = report.get("summary")
    if summary is not None:
        got = {k: summary.get(src) for k, src in SUMMARY_KEYS.items()}
        if any(v is None for v in got.values()):
            return None
        return {k: int(v) for k, v in got.items()}
    outcomes = report.get("outcomes")
    if outcomes is None:
        return None
    return {k: sum(1 for o in outcomes if o == k) for k in OUTCOMES}


class RunListView(ReceiptView):
    name = "run_list"
    receipt = RUN_INDEX
    reads = (
        "directory_shown",
        # Present only for `oneground ui --demo`. Declared here rather than
        # rendered from the server so the label travels inside the drawing
        # and survives a screenshot, as the lab's projection caption does.
        "demo.label",
        "demo.way_out",
        "demo.fetched_note",
        "demo.not_available",
        "runs[].name",
        "runs[].n_base",
        "runs[].dimension",
        "runs[].stages",
        "runs[].problems",
        "runs[].report.tier",
        "runs[].report.headline",
        "runs[].report.recommended",
        "runs[].report.summary",
        "runs[].report.outcomes",
        "runs[].version.version",
        "runs[].version.reason",
        "runs[].manifest.all_verified",
        "runs[].manifest.failing",
        "runs[].manifest.note",
    )

    def render(self, f):
        names, sizes, dims, stages = [], [], [], []
        tiers, headlines, verdicts = [], [], []
        meets, fails, cc, counted = [], [], [], []
        versions, version_reasons = [], []
        verified, failing, trouble, why = [], [], [], []

        for row in f.each("runs"):
            names.append(row["name"])
            # Carried across as recorded. A Tier-2 run declares its corpus
            # rather than measuring it, so this is the sentence
            # "couldnt_check: declared, not measured" and not a number.
            sizes.append(row["n_base"] if row.has("n_base") else None)
            dims.append(row["dimension"] if row.has("dimension") else None)
            st = row["stages"]
            stages.append([s for s in STAGES if st.get(s)])

            tier = row["report.tier"] if row.has("report.tier") else None
            tiers.append(tier)
            headlines.append(row["report.headline"]
                             if row.has("report.headline") else None)
            verdicts.append(row["report.recommended"]
                            if row.has("report.recommended") else None)

            report = None
            if tier is not None:
                report = {
                    "summary": (row["report.summary"]
                                if row.has("report.summary") else None),
                    "outcomes": (row["report.outcomes"]
                                 if row.has("report.outcomes") else None),
                }
            c = _counts(report)
            counted.append(c is not None)
            # Always all three, including zeros; None only when there is no
            # report at all, which the column renders as "not reported"
            # rather than as three zeros.
            meets.append(c["meets"] if c else None)
            fails.append(c["fails"] if c else None)
            cc.append(c["couldnt_check"] if c else None)

            versions.append(row["version.version"])
            version_reasons.append(row["version.reason"])
            verified.append(row["manifest.all_verified"])
            failing.append(row["manifest.failing"])
            # Present when there is no MANIFEST at all: absent is couldnt_check,
            # not "failed", and the reason is what the reader acts on.
            why.append(row["manifest.note"] if row.has("manifest.note")
                       else None)
            trouble.append(list(row["problems"]))

        marks = [Mark(kind="row",
                      data={"name": names, "n_base": sizes,
                            "dimension": dims, "stages": stages,
                            "tier": tiers, "headline": headlines,
                            "recommended": verdicts,
                            "meets": meets, "fails": fails,
                            "couldnt_check": cc, "counted": counted,
                            "version": versions,
                            "version_reason": version_reasons,
                            "verified": verified, "failing": failing,
                            "manifest_note": why, "problems": trouble},
                      encoding={"label": "name"})]

        figures = {"directory": f["directory_shown"], "n_runs": len(names),
                   "outcome_order": list(OUTCOMES)}
        if f.has("demo.label"):
            figures["demo"] = {
                "label": f["demo.label"],
                "way_out": f["demo.way_out"],
                "fetched_note": f["demo.fetched_note"],
                "not_available": f["demo.not_available"],
            }
        gaps = {}
        unverified = [n for n, v in zip(names, verified) if v is not True]
        if unverified:
            # Not a gap in the drawing -- the rows are still drawn -- but the
            # page must not present the set as sound.
            figures["unverified"] = unverified
        if not names:
            gaps["runs"] = gap(f"no workdir under {f['directory_shown']}; a run "
                               "directory holds one directory per run")
        return Drawing(view=self.name, marks=marks, figures=figures,
                       gaps=gaps,
                       caption=f"{len(names)} run(s) under this directory, "
                               "each listed with its own digest verification")
