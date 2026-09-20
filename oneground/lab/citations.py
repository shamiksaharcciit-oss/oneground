"""Resolving a report's citations against the receipts they name (task 041).

Transport for the evidence drawer. The drawer shows, for any figure, the file
and field it was read from and the value at that field; the ruling on this
task is that it may not import `oneground/report/claims.py`, because
`oneground.report` is in the guard's MEASURING list. So a citation is resolved
by parsing its `source` string and looking the field up in the receipt it
names -- using `receipt.split_path`, the one grammar, so that a view's
declared `reads` and a claim's `source` are written the same way and never
need translating between notations.

THE THREE NON-FIELD KINDS ARE NOT FAILURES
------------------------------------------
Step 5's acceptance originally asked that every entry resolve to a real field
in a real file. Three sources in a real report cannot, and should not:

    (rule)                     the recommendation follows from a rule, not
                               from a row -- there is no field to point at
    requirements:constraints   the requirements YAML, which is an input the
                               user wrote, not a receipt a stage produced
    options[*].judgement       a wildcard: the claim is about every option,
                               not about one field of one

Rendering these as links that quietly do nothing would teach a reader the
wrong thing about what a citation is -- that some of them are simply broken.
They are named kinds, and the drawer renders each visibly differently.

A fourth outcome is a real failure and is reported as one: a source naming a
file or field that is not there.

WHAT THIS MODULE DOES NOT DO
----------------------------
It does not compare. It carries the value the claim cites and the value at the
field the claim names, both recorded, and the view compares them -- because a
comparison shown on a page is a drawing, and the contract puts drawing in
views. That split is why the citation defect this task found is visible at
all: two recorded values arriving side by side, with nothing in between them
deciding which to believe.
"""

import json
import os

from .receipt import CITATIONS, split_path

#: A source that is not a `file:field` reference, and what it is instead.
#: Each is a kind the drawer renders in its own right.
NON_FIELD = {
    "(rule)": ("rule",
               "this follows from a rule, not from a row: no measurement was "
               "read to reach it"),
    "(not run)": ("not_run",
                  "the stage that would have produced this was not run"),
    "cost": ("cost_model",
             "the cost model, which is declared prices rather than a "
             "measurement"),
}

#: Sources naming something that is not a receipt of this run.
REQUIREMENTS_PREFIX = "requirements:"

#: Fields a list member may be identified by, as `receipt.MEMBER_KEYS`.
MEMBER_KEYS = ("config", "engine", "label", "name", "key")


def _segment(seg):
    if seg.endswith("]") and "[" in seg:
        head, _, rest = seg.partition("[")
        return head, rest[:-1]
    return seg, None


def _member(node, want):
    for it in node:
        if isinstance(it, dict) and any(it.get(k) == want
                                        for k in MEMBER_KEYS):
            return it
    return None


def _walk(node, path, member=None):
    """(found, value, reason). Never raises: unresolvable is an answer."""
    for seg in split_path(path):
        head, want = _segment(seg)
        if isinstance(node, dict):
            if head not in node:
                return False, None, (
                    f"no field {head!r} here (this receipt has "
                    f"{sorted(node)[:5]})")
            node = node[head]
        elif isinstance(node, list) and member is not None:
            got = _member(node, member)
            if got is None:
                return False, None, f"no member {member!r} in this list"
            if head not in got:
                return False, None, f"no field {head!r} on member {member!r}"
            node = got[head]
        else:
            return False, None, f"cannot read {head!r} from a {type(node).__name__}"
        if want is None:
            continue
        if want == "*":
            return False, None, "names every option, not one field"
        if isinstance(node, list):
            got = _member(node, want)
            if got is None:
                return False, None, f"no member {want!r} in a list of {len(node)}"
            node = got
        elif isinstance(node, dict):
            if want not in node:
                return False, None, f"no key {want!r}"
            node = node[want]
        else:
            return False, None, f"cannot index a {type(node).__name__}"
    return True, node, None


def _contains(container, value):
    """Where `value` sits inside `container`, or None.

    Some sources name a container and cite a leaf inside it --
    `latency_shape_single_client.p95_across_runs` holds min/median/max and the
    claim cites the min. That is an under-specified source rather than a wrong
    one, and saying so is more useful than calling it a mismatch.
    """
    if isinstance(container, dict):
        for k, v in container.items():
            if v == value:
                return k
    return None


def _scoped(data, path, member):
    """Enter `engines[member]` when a source starts below that level.

    `verify.json:load.achieved_qps` names no engine; the citation's `member`
    does. Descending by the member rather than guessing is what makes a
    two-engine run's citations unambiguous.
    """
    if not (isinstance(data, dict) and "engines" in data and member):
        return data
    first = split_path(path)[0] if path else ""
    head, _ = _segment(first)
    if head in data:
        return data
    engines = data["engines"]
    if isinstance(engines, list):
        got = _member(engines, member)
        if got is not None:
            return got
    elif isinstance(engines, dict) and member in engines:
        return engines[member]
    return data


def resolve_one(workdir, source, cited_value=None, member=None, cache=None):
    """One citation, resolved. Returns the drawer's entry for it.

    `kind` is always set and is what the drawer renders on: `field`,
    `within`, `rule`, `not_run`, `cost_model`, `requirements`, `every_option`
    or `unresolved`. Nothing here decides whether a `field` entry agrees with
    its cited value -- both values are carried and the view compares them.
    """
    entry = {"source": source, "member": member, "cited_value": cited_value,
             "file": None, "path": None, "field_value": None,
             "found": False, "kind": None, "note": None, "within": None}

    if not source:
        entry.update(kind="unresolved", note="this claim cites no source")
        return entry
    if source in NON_FIELD:
        kind, note = NON_FIELD[source]
        entry.update(kind=kind, note=note)
        return entry
    if source.startswith(REQUIREMENTS_PREFIX):
        entry.update(kind="requirements", path=source.partition(":")[2],
                     note="the requirements file you wrote, which is an "
                          "input rather than a receipt a stage produced")
        return entry
    if ":" not in source:
        entry.update(kind="unresolved",
                     note=f"{source!r} is not a file:field reference")
        return entry

    fname, _, path = source.partition(":")
    entry.update(file=fname, path=path)
    if not fname.endswith(".json"):
        entry.update(kind="unresolved",
                     note=f"{fname} is not a json receipt of this run")
        return entry

    if cache is not None and fname in cache:
        data = cache[fname]
    else:
        full = os.path.join(workdir, fname)
        if not os.path.isfile(full):
            entry.update(kind="unresolved",
                         note=f"{fname} is not in this run directory")
            return entry
        try:
            with open(full, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            entry.update(kind="unresolved",
                         note=f"{fname} could not be read: "
                              f"{e.__class__.__name__}")
            return entry
        if cache is not None:
            cache[fname] = data

    found, value, why = _walk(_scoped(data, path, member), path, member)
    if not found:
        if why == "names every option, not one field":
            entry.update(kind="every_option",
                         note="this claim is about every option, not about "
                              "one field of one")
            return entry
        entry.update(kind="unresolved", note=why)
        return entry

    entry.update(found=True, field_value=value)
    if isinstance(value, (dict, list)) and cited_value is not None:
        where = _contains(value, cited_value)
        if where is not None:
            entry.update(kind="within", within=where,
                         note=f"the source names the block; the cited figure "
                              f"is its {where!r}")
            return entry
    entry.update(kind="field")
    return entry


def _declared_citations(workdir, report, cache):
    """A Tier-2 report, in the same shape as a Tier-1 one.

    `run_declared` writes no claims and no options: it records a flat
    `constraints` list in which every outcome is `couldnt_check` by
    construction, because the corpus was described rather than sampled. Each
    of those becomes one claim here, so the drawer draws one shape rather than
    two and the equal-weight rule has nothing to make an exception for.

    Nothing is composed. A constraint's `reason` is the report's own sentence
    and its `source` is the report's own citation -- which for this tier is
    `characterization.json:declared`, pointing at the block that says the
    corpus was declared. That resolves, and a reader who follows it arrives at
    the declaration rather than at a measurement, which is the correct and
    slightly uncomfortable answer.
    """
    out = []
    for i, c in enumerate(report.get("constraints") or []):
        if not isinstance(c, dict):
            continue
        entry = resolve_one(workdir, c.get("source"), None, None, cache)
        out.append({
            "index": i,
            "kind": "declared_constraint",
            "text": f"{c.get('constraint')}: {c.get('reason')}",
            "constraint": c.get("constraint"),
            "outcome": c.get("outcome"),
            "remedy": {
                "couldnt_check_kind": c.get("kind"),
                "remedy": report.get("recommendation_reason"),
                "source": "report.json:recommendation_reason",
                "scope": "the whole run",
                "note": "Tier 2 measured nothing on this corpus, so the "
                        "remedy is the same for every constraint: sample it",
            },
            "entries": [entry],
        })
    return {"kind": CITATIONS, "workdir": workdir, "run": report.get("run"),
            "tier": report.get("tier"), "claims": out}


def _remedies(report):
    """{(config, constraint): {kind, remedy}} from the options' judgements.

    A couldn't-check claim says what could not be decided; the remedy that
    would settle it is recorded one level away, on the option's judgement, as
    `couldnt_check_kind` and `remedy`. The drawer has to reach it, because
    selecting a couldn't-check is meant to be the most informative click on
    the page and a reason without a remedy ends in nothing the reader can do.

    Carried across, not composed: the sentence is the report's own.
    """
    out = {}
    for opt in report.get("options") or []:
        config = opt.get("config")
        judgement = opt.get("judgement") or {}
        for c in judgement.get("constraints") or []:
            if not isinstance(c, dict):
                continue
            if c.get("remedy") or c.get("couldnt_check_kind"):
                out[(config, c.get("constraint"))] = {
                    "couldnt_check_kind": c.get("couldnt_check_kind"),
                    "remedy": c.get("remedy"),
                    "source": f"report.json:options[{config}]."
                              f"judgement.constraints[{c.get('constraint')}]",
                }
    return out


def _remedy_for(claim, table):
    """The remedy for one claim, matched on the option it holds for.

    A claim holding for several options is not given one of theirs: the
    drawer would be showing a remedy for a configuration the reader did not
    select. It gets None, and the page says the remedy is recorded per
    option.
    """
    constraint = claim.get("constraint")
    if not constraint:
        return None
    holds = claim.get("holds_for") or ([claim["subject"]]
                                       if claim.get("subject") else [])
    hits = [table[(c, constraint)] for c in holds
            if (c, constraint) in table]
    if len(hits) == 1:
        return hits[0]
    if hits:
        return {"couldnt_check_kind": None, "remedy": None,
                "source": None, "scope": "several",
                "note": "this claim holds for several configurations and the "
                        "remedy is recorded per configuration; open one to "
                        "see its own"}
    if holds:
        return None
    # A claim scoped to no option -- `to_resolve` is report-wide -- still has
    # a remedy if every option records the same one for that constraint.
    # Identical text across all of them is one fact about the run, not eight
    # facts about eight configurations; different text is not summarised.
    same = {t["remedy"] for (_, c), t in table.items()
            if c == constraint and t.get("remedy")}
    if len(same) == 1:
        one = next(t for (_, c), t in table.items()
                   if c == constraint and t.get("remedy"))
        return {**one, "scope": "every option",
                "note": "every configuration records this same remedy, so it "
                        "is a fact about the run rather than about one of "
                        "them"}
    return None


def resolve_citations(workdir, report):
    """Every claim in `report`, with every citation resolved.

    A claim with no `cites` is not skipped: its own `source` is resolved
    instead, so that **every claim gets an entry**. A claim with neither gets
    an entry saying so, because a claim the drawer is silent about is
    indistinguishable from one the drawer failed to load.
    """
    workdir = os.path.abspath(workdir)
    cache = {}
    claims = report.get("claims")
    if claims is None:
        return _declared_citations(workdir, report, cache)
    table = _remedies(report)
    out = []
    for i, claim in enumerate(claims):
        cites = claim.get("cites") or []
        entries = [resolve_one(workdir, c.get("source"), c.get("value"),
                               c.get("member"), cache) for c in cites]
        if not entries:
            entries = [resolve_one(workdir, claim.get("source"), None,
                                   None, cache)]
        out.append({
            "index": i,
            "kind": claim.get("kind"),
            "text": claim.get("text"),
            "constraint": claim.get("constraint"),
            "outcome": claim.get("asserts_outcome"),
            "remedy": _remedy_for(claim, table),
            "entries": entries,
        })
    return {"kind": CITATIONS, "workdir": workdir,
            "run": report.get("run"), "tier": 1 if claims else None,
            "claims": out}
