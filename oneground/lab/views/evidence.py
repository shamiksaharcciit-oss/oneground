"""The evidence drawer: every claim, and what each one cites (task 041, step 5).

A view over `citations.resolve_citations`'s document. It draws, for every
claim in a report, the file and field each figure was read from, the value at
that field, and — for a couldn't-check — what would settle it.

**Every claim gets an entry, and every entry says what kind of thing it
points at.** That is the shape step 5 was reformulated into, because three
sources in a real report are legitimately not fields and one is a genuine
miss:

    field         a receipt field, resolved; the value is shown beside the
                  cited one
    within        the source names a block and the cited figure is one of its
                  members; the member is named
    rule          `(rule)` -- this follows from a rule, not from a row
    requirements  the requirements file, an input rather than a receipt
    every_option  a wildcard: about every option, not one field of one
    not_run       the stage that would have produced it was not run
    cost_model    declared prices rather than a measurement
    unresolved    the source names a file or field that is not there

**Only `field` and `within` are navigable**, and the drawing says so per
entry. A reader who selects `(rule)` and gets an inert link learns that some
citations are simply broken; a reader who selects it and is told *this follows
from a rule, not from a row* learns what the project means by a citation. The
difference is the whole point of rendering the kinds apart.

**The comparison happens here, not in transport.** The document carries the
value the claim cites and the value at the field it names; this view compares
them and sets `agrees`. That is deliberate: the citation defect this task
found is exactly an `agrees: false`, and putting the comparison in the view
means the page shows both numbers rather than a verdict about them.
"""

from ..contract import Drawing, Mark
from ..receipt import CITATIONS, ReceiptView, gap

#: Entry kinds that point at a real field a reader can open.
NAVIGABLE = ("field", "within")

#: Every kind the drawer renders, so a page can be checked for covering them
#: all rather than falling through to a default.
KINDS = ("field", "within", "rule", "requirements", "every_option",
         "not_run", "cost_model", "unresolved")

COULDNT_CHECK = "couldnt_check"

#: Claim kinds that ARE a couldn't-check, for a report that records the
#: outcome in the kind rather than in `asserts_outcome`. Tier 1 leaves
#: `asserts_outcome` null on every claim and says "to_resolve"; Tier 2 records
#: the outcome directly. Selecting on a recorded field either way -- nothing
#: here decides an outcome, it reads the one that was written.
COULDNT_CHECK_KINDS = ("to_resolve", "declared_constraint")


def _is_couldnt_check(kind, outcome):
    return outcome == COULDNT_CHECK or kind in COULDNT_CHECK_KINDS


def _agrees(kind, cited, at_field):
    """Whether the cited figure and the field agree. None when not comparable.

    `None` is not "yes". A claim that cites no value has nothing to compare,
    and saying so is different from saying the two matched.
    """
    if kind == "within":
        return True
    if kind != "field" or cited is None:
        return None
    if isinstance(at_field, (dict, list)):
        return False
    if isinstance(cited, (int, float)) and isinstance(at_field, (int, float)) \
            and not isinstance(cited, bool) and not isinstance(at_field, bool):
        return abs(float(cited) - float(at_field)) <= \
            1e-9 * max(1.0, abs(float(at_field)))
    return cited == at_field


class EvidenceDrawerView(ReceiptView):
    name = "evidence_drawer"
    receipt = CITATIONS
    reads = (
        "run",
        "tier",
        "claims[].index",
        "claims[].kind",
        "claims[].text",
        "claims[].constraint",
        "claims[].outcome",
        "claims[].remedy",
        "claims[].entries[].source",
        "claims[].entries[].member",
        "claims[].entries[].cited_value",
        "claims[].entries[].field_value",
        "claims[].entries[].file",
        "claims[].entries[].path",
        "claims[].entries[].kind",
        "claims[].entries[].note",
        "claims[].entries[].within",
    )

    def render(self, f):
        idx, kinds, texts, constraints, outcomes = [], [], [], [], []
        remedies, n_entries, entry_rows = [], [], []
        no_entry = []

        for claim in f.each("claims"):
            i = claim["index"]
            idx.append(i)
            kinds.append(claim["kind"])
            texts.append(claim["text"])
            constraints.append(claim["constraint"])
            outcomes.append(claim["outcome"])
            remedies.append(claim["remedy"])

            mine = []
            for e in claim.each("entries"):
                kind = e["kind"]
                cited = e["cited_value"]
                at_field = e["field_value"]
                mine.append({
                    "claim": i,
                    "source": e["source"],
                    "member": e["member"],
                    "file": e["file"],
                    "path": e["path"],
                    "kind": kind,
                    "note": e["note"],
                    "within": e["within"],
                    "cited_value": cited,
                    "field_value": at_field,
                    # the comparison is the drawing, not the lookup
                    "agrees": _agrees(kind, cited, at_field),
                    # a reader may open this one; the others are not links
                    "navigable": kind in NAVIGABLE,
                })
            n_entries.append(len(mine))
            if not mine:
                no_entry.append(i)
            entry_rows.extend(mine)

        marks = [
            Mark(kind="row",
                 data={"index": idx, "kind": kinds, "text": texts,
                       "constraint": constraints, "outcome": outcomes,
                       "remedy": remedies, "n_entries": n_entries},
                 encoding={"label": "text"}),
            Mark(kind="row",
                 data={"claim": [e["claim"] for e in entry_rows],
                       "source": [e["source"] for e in entry_rows],
                       "member": [e["member"] for e in entry_rows],
                       "file": [e["file"] for e in entry_rows],
                       "path": [e["path"] for e in entry_rows],
                       "kind": [e["kind"] for e in entry_rows],
                       "note": [e["note"] for e in entry_rows],
                       "within": [e["within"] for e in entry_rows],
                       "cited_value": [e["cited_value"] for e in entry_rows],
                       "field_value": [e["field_value"] for e in entry_rows],
                       "agrees": [e["agrees"] for e in entry_rows],
                       "navigable": [e["navigable"] for e in entry_rows]},
                 encoding={"label": "source"}),
        ]

        by_kind = {k: sum(1 for e in entry_rows if e["kind"] == k)
                   for k in KINDS}
        disagreeing = [e["source"] for e in entry_rows
                       if e["agrees"] is False]
        couldnt = [i for i, k, o in zip(idx, kinds, outcomes)
                   if _is_couldnt_check(k, o)]
        figures = {
            "run": f["run"],
            "tier": f["tier"],
            "n_claims": len(idx),
            "n_entries": len(entry_rows),
            "entry_kinds": by_kind,
            "kinds_rendered": list(KINDS),
            "navigable_kinds": list(NAVIGABLE),
            # Named, not counted away: an entry whose cited figure and whose
            # field disagree is the thing this drawer exists to make visible.
            "disagreeing": disagreeing,
            "couldnt_check_claims": couldnt,
            "couldnt_check_without_remedy": [
                i for i, k, o, r in zip(idx, kinds, outcomes, remedies)
                if _is_couldnt_check(k, o) and not (r or {}).get("remedy")],
        }
        gaps = {}
        if no_entry:
            gaps["entries"] = gap(
                f"claims {no_entry} carry no citation at all; a claim the "
                "drawer is silent about cannot be told apart from one it "
                "failed to load")
        if not idx:
            gaps["claims"] = gap("this report records no claims")
        return Drawing(view=self.name, marks=marks, figures=figures,
                       gaps=gaps,
                       caption=(f"{len(idx)} claim(s), {len(entry_rows)} "
                                "citation(s); only field and within entries "
                                "open onto a receipt"))
