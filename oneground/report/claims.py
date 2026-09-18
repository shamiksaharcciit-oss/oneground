"""Claims: a sentence about rows, structured before it is prose.

WHY THIS MODULE EXISTS
----------------------
Three tasks running produced the same defect, and both shipped:

  task 015   `and both carry {best.outcome}` -- the WINNER's verdict asserted
             of every engine. The report said "both carry meets" about a
             pgvector row that sustained 112.63 of an offered 200.
  task 017e  `_options_table` rendered `verdict_for(name)`, the FIRST verdict
             for a constraint. A configuration whose p95 met the budget on
             Qdrant and missed it on pgvector by forty times rendered one flat
             green `meets` cell, with the failing number nowhere on the page.

Neither was caught, and the reason is structural rather than careless. The
measurement layer has an external oracle -- exact k-NN, a digest, a published
value -- so a wrong number *moves* and something notices. The presentation
layer has none: "does this sentence say something true about these rows" is
not computable from the rows once the sentence is a string. So every test that
existed asserted **presence** -- the names appear, the page renders, no
verdict word shows up in a couldnt_check row -- rather than **correspondence**.

Task 018 fixed coverage: every rendering path is now known and driven. It did
not give the layer an oracle. This module is the oracle.

THE RULE
--------
**A sentence about rows is built as a `Claim` and rendered from it.** The
Claim carries what the sentence asserts, of whom, citing which values from
which source fields -- so "is this true" becomes a computation over the same
rows the report was built from, and `check()` performs it.

A written rule does not fail a build. `collapse_by_constraint`'s docstring
stated the precondition it was violating: *"it is only safe because the
decision log names the engine every time"*. It did not name the engine every
time. This is that rule, executable.

See `docs/CLAIMS.md`.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# quantifiers
# --------------------------------------------------------------------------
# A claim is about a SET. What makes it true depends on how it quantifies:
#
#   UNIVERSAL    admissible only if the predicate holds for every member
#   EXISTENTIAL  admissible if it holds for at least one, and it must name
#                which -- "the better of two" without saying which is not a
#                statement a reader can use
#   NEGATION     a denial of a universal. Checked as a denial, never as the
#                assertion it contains: task 017f shipped a guard that matched
#                "the verdicts differ" as if it were a uniformity claim,
#                because the word "differ" sat next to the word "carry". A
#                guard that cannot tell an assertion from its negation is
#                worse than no guard.
#   NONE         about one named member, or about no member at all

UNIVERSAL = "universal"
EXISTENTIAL = "existential"
NEGATION = "negation"
NONE = "none"

QUANTIFIERS = (UNIVERSAL, EXISTENTIAL, NEGATION, NONE)

# Surface forms, used only to audit prose that a Claim rendered -- never to
# decide what a Claim means. The Claim says what it quantifies; these catch a
# renderer that wrote a word the Claim did not authorise.
UNIVERSAL_WORDS = ("both", "all", "every", "each", "neither", "none")
EXISTENTIAL_WORDS = ("one of", "the better of", "only", "at least one")

# The denials, longest first so a negation is recognised before the universal
# word inside it is. `_strip_negations` removes these before the universal
# search, which is what makes "the verdicts differ" and "this is not true of
# every engine measured" legal sentences rather than violations.
NEGATION_PHRASES = (
    "is not true of every engine measured",
    "not true of every engine",
    "does not all carry",
    "do not all carry",
    "not every",
    "do not all",
    "does not all",
    "the verdicts differ",
    "fewer than two",
    "is not indistinguishable",
    "indistinguishable on recall is not",
    "not on all of them",
    "does not on",
)


def _strip_negations(text):
    t = " ".join(str(text).lower().split())
    for phrase in NEGATION_PHRASES:
        t = t.replace(phrase, " ")
    return t


def universal_words_in(text):
    """Universal quantifier words that survive negation-stripping."""
    t = _strip_negations(text)
    return tuple(w for w in UNIVERSAL_WORDS
                 if re.search(r"\b%s\b" % re.escape(w), t))


# --------------------------------------------------------------------------
# what a claim cites
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Cite:
    """One value the claim rests on, and the field it came from.

    `source` is a path into the run's own artifacts -- `verify.json:engines
    [qdrant].load.achieved_qps`, `simulate.json:rows[cfg].recall_at_10` -- so
    `check()` can go and read it. A cite whose value does not equal what is at
    its source is the defect this whole module exists to catch, in its
    simplest form: a number that came from somewhere else.
    """

    member: str                      # who this value is about: engine or config
    value: Any = None
    source: str = ""
    outcome: Optional[str] = None
    constraint: Optional[str] = None
    reason: str = ""                 # the verdict's own words; carries no claim

    def as_dict(self):
        return {"member": self.member, "value": self.value,
                "source": self.source, "outcome": self.outcome,
                "constraint": self.constraint, "reason": self.reason}


@dataclass
class Claim:
    """A sentence about rows, before it is a sentence.

    `scope` is every member the claim is about. `holds_for` is the subset the
    predicate is true of, computed from the rows by the caller -- never from
    the winner, which is exactly how `{best.outcome}` went wrong.
    """

    kind: str                         # the decision-log kind, for the reader
    predicate: str                    # what is asserted: "meets", "fails", ...
    quantifier: str = NONE
    subject: Optional[str] = None     # the configuration, where there is one
    constraint: Optional[str] = None
    scope: Tuple[str, ...] = ()
    holds_for: Tuple[str, ...] = ()
    cites: Tuple[Cite, ...] = ()
    text: str = ""                    # rendered from this Claim, by render()
    source: str = ""
    environment: Optional[str] = None
    # The outcome this claim asserts of its members, where it asserts one.
    # Set it and `check()` stops trusting `holds_for` and recomputes it from
    # the rows -- which is the difference between a claim that is checked and
    # a claim that asserts its own truth condition.
    asserts_outcome: Optional[str] = None
    # Which rule turns rows into `holds_for`. See `_derive_holds`.
    holds_rule: str = "any"
    detail: str = ""                  # reasons and caveats; carries no claim
    # A sentence that asserts several things is several claims. Each part
    # carries its own quantifier, its own set and its own fragment of the
    # prose, because "both" means something only at the grain of the clause
    # that contains it: "Both were measured" quantifies over the engines and
    # "meets every constraint that could be checked" over the constraints,
    # and one `quantifier` field cannot be true of both.
    parts: Tuple["Claim", ...] = ()
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self):
        return {
            "kind": self.kind, "predicate": self.predicate,
            "quantifier": self.quantifier, "subject": self.subject,
            "constraint": self.constraint,
            "scope": list(self.scope), "holds_for": list(self.holds_for),
            "cites": [c.as_dict() for c in self.cites],
            "text": self.text, "source": self.source,
            "environment": self.environment,
            "asserts_outcome": self.asserts_outcome,
            "holds_rule": self.holds_rule, "detail": self.detail,
            "parts": [p.as_dict() for p in self.parts],
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            kind=d.get("kind", ""), predicate=d.get("predicate", ""),
            quantifier=d.get("quantifier", NONE), subject=d.get("subject"),
            constraint=d.get("constraint"),
            scope=tuple(d.get("scope") or ()),
            holds_for=tuple(d.get("holds_for") or ()),
            cites=tuple(Cite(**c) for c in (d.get("cites") or [])),
            text=d.get("text", ""), source=d.get("source", ""),
            environment=d.get("environment"),
            asserts_outcome=d.get("asserts_outcome"),
            holds_rule=d.get("holds_rule", "any"),
            detail=d.get("detail", ""),
            parts=tuple(cls.from_dict(x) for x in (d.get("parts") or [])),
            extra=dict(d.get("extra") or {}))

    # -- the log entry shape the rest of the report already speaks ----------
    def as_entry(self):
        return {"kind": self.kind, "text": self.text, "source": self.source}


# --------------------------------------------------------------------------
# the invariant
# --------------------------------------------------------------------------

class ClaimViolation(Exception):
    """A claim that does not follow from the rows it cites."""


def composed_text(claim):
    """The prose the renderer composed, with verbatim quotations removed.

    `Verdict.reason` and `Claim.detail` are quotations from the layer that
    measured the values. They are audited where they are produced. What is
    audited here is what this layer ADDED -- a quantifier or a number the
    renderer chose.
    """
    text = claim.text or ""
    quoted = [claim.detail or ""]
    quoted += [c.reason or "" for c in claim.cites]
    quoted += [str((claim.extra or {}).get("not_on_every_engine") or "")]
    for q in quoted:
        q = q.strip()
        if len(q) > 3:
            text = text.replace(q, " ")
    return text


def _fmt(v):
    if isinstance(v, float):
        return "%.2f" % v
    return str(v)


def _derive_holds(rule, outcome, outcomes):
    """Does the predicate hold for a member with these per-constraint outcomes?

    Named rules rather than one implied by the caller, because "meets
    somewhere" and "meets everywhere" are different sentences and both get
    written as "meets".
    """
    if rule == "all":
        return all(o == outcome for o in outcomes)
    if rule == "no_fails":
        # Mirrors `verdict.engines_meeting`: an engine that failed anything is
        # out, and one whose verdicts are all couldnt_check is not in either,
        # because could-not-check is not a pass.
        return ("fails" not in outcomes) and (outcome in outcomes)
    if rule == "any":
        return outcome in outcomes
    raise ClaimViolation("unknown holds_rule %r" % rule)


def check(claim, rows=None, tolerance=1e-9):
    """Every way a claim can fail to follow from its rows. Returns a list.

    `rows` is `{member: {constraint: {"value":, "outcome":, "source":}}}` --
    the same per-member facts the claim was built from. Passing it is what
    turns "the claim is internally consistent" into "the claim is true of the
    run", and the second is the one that matters.
    """
    bad = []
    q = claim.quantifier
    if q not in QUANTIFIERS:
        bad.append("unknown quantifier %r" % q)

    scope, holds = set(claim.scope), set(claim.holds_for)

    # 1. holds_for is part of scope. A claim true of somebody outside the set
    #    it is about is not a claim about that set.
    outside = holds - scope
    if outside:
        bad.append("holds_for names members outside scope: %s"
                   % sorted(outside))

    # 2. every member quantified over appears in the cited rows.
    cited = {c.member for c in claim.cites}
    if scope and not scope <= cited:
        bad.append("scope members with no cited row: %s"
                   % sorted(scope - cited))

    # 3. the quantifier rule.
    if q == UNIVERSAL and scope and holds != scope:
        bad.append(
            "universal claim %r over %s holds only for %s"
            % (claim.predicate, sorted(scope), sorted(holds) or "nobody"))
    if q == EXISTENTIAL:
        if not holds:
            bad.append("existential claim %r holds for nobody"
                       % claim.predicate)
        else:
            unnamed = [m for m in sorted(holds) if str(m) not in claim.text]
            if claim.text and unnamed:
                bad.append(
                    "existential claim does not name the members it holds "
                    "for: %s" % unnamed)

    # 4. prose may not carry a universal word the claim did not authorise.
    #
    #    A composite delegates this to its parts, because a universal word
    #    belongs to the clause it sits in: "Both were measured" is universal
    #    over the engines while the sentence around it is existential about
    #    which one is better. Both statements are true and a single audit of
    #    the whole sentence can only be wrong about one of them.
    if claim.parts:
        for part in claim.parts:
            if part.subject is None:
                # A part is about its parent's option. Without this every
                # part would fall back to the run-level rows and check
                # against the wrong ones -- quietly, and in the direction of
                # passing.
                part.subject = claim.subject
            if "literal_numbers" in (claim.extra or {}):
                # A configured constant the sentence quotes -- the calibration
                # tolerance, say -- belongs to the whole sentence, so the
                # fragment that prints it inherits the declaration.
                part.extra.setdefault("literal_numbers",
                                      claim.extra["literal_numbers"])
            if part.text and part.text not in claim.text:
                bad.append(
                    "part %r renders %r, which is not in the sentence -- a "
                    "part that is not in the prose is decoration and audits "
                    "nothing" % (part.predicate, part.text[:60]))
            bad.extend("part(%s): %s" % (part.predicate, m)
                       for m in check(part, rows, tolerance))
    elif claim.text:
        words = universal_words_in(composed_text(claim))
        if words and q not in (UNIVERSAL, NEGATION):
            bad.append("prose uses universal word(s) %s but the claim is %s"
                       % (list(words), q))

    # 5. every cited value equals the value at its stated source field.
    if rows is not None:
        here = rows.for_claim(claim) if isinstance(rows, RowIndex) else rows
        for c in claim.cites:
            facts = (here.get(c.member) or {})
            key = c.constraint if c.constraint is not None else claim.constraint
            got = facts.get(key) if key is not None else None
            if got is None:
                continue                     # nothing recorded to check against
            if c.value is not None and got.get("value") is not None:
                try:
                    same = abs(float(c.value) - float(got["value"])) <= tolerance
                except (TypeError, ValueError):
                    same = c.value == got["value"]
                if not same:
                    bad.append(
                        "cited %s for %s/%s but the row says %s"
                        % (_fmt(c.value), c.member, key, _fmt(got["value"])))
            if (c.outcome is not None and got.get("outcome") is not None
                    and c.outcome != got["outcome"]):
                bad.append("cited outcome %s for %s/%s but the row says %s"
                           % (c.outcome, c.member, key, got["outcome"]))
            if (c.source and got.get("source")
                    and c.source != got["source"]):
                bad.append("cited source %s for %s/%s but the row says %s"
                           % (c.source, c.member, key, got["source"]))

    # 5b. `holds_for` is RECOMPUTED, not believed.
    #
    #     A mutant that set `quantifier=UNIVERSAL` and `holds_for=scope`
    #     survived the first mutation run, because every rule above read
    #     `holds_for` as given. A claim that supplies its own truth condition
    #     is not being checked. Where the claim says which outcome it asserts,
    #     the set it holds for is derived from the rows and the claim's answer
    #     is compared against it.
    if rows is not None and claim.asserts_outcome and scope:
        here = rows.for_claim(claim) if isinstance(rows, RowIndex) else rows
        derived, unknown = set(), set()
        for member in scope:
            facts = here.get(member) or {}
            if claim.constraint is not None:
                got = facts.get(claim.constraint)
                outcomes = [got.get("outcome")] if got else []
            else:
                outcomes = [f.get("outcome") for f in facts.values()
                            if isinstance(f, dict)]
            outcomes = [o for o in outcomes if o is not None]
            if not outcomes:
                unknown.add(member)
            elif _derive_holds(claim.holds_rule, claim.asserts_outcome,
                               outcomes):
                derived.add(member)
        checkable = scope - unknown
        if checkable and (holds & checkable) != (derived & checkable):
            bad.append(
                "claims to hold for %s but the rows say %s"
                % (sorted(holds & checkable) or "nobody",
                   sorted(derived & checkable) or "nobody"))

    # 6. a value quoted in the prose must be one the claim cites, AND must be
    #    cited for the member it is printed next to.
    if claim.text and claim.cites:
        quoted = set(re.findall(r"\d+\.\d{2}\b", composed_text(claim)))
        allowed = set()
        for c in claim.cites:
            if isinstance(c.value, (int, float)) and not isinstance(c.value,
                                                                   bool):
                allowed.add("%.2f" % float(c.value))
                allowed.add("%.4f" % float(c.value))
        for token in claim.extra.get("literal_numbers", ()):
            allowed.add(str(token))
        stray = {n for n in quoted if n not in allowed
                 and not any(a.startswith(n) for a in allowed)}
        if stray:
            bad.append("prose quotes %s, which the claim does not cite"
                       % sorted(stray))

    # 7. a number printed beside a member's name must be THAT member's.
    #
    #    "is it cited anywhere" is not the question; "is it cited for this
    #    member" is. A mutant that swapped two engines' values passed the
    #    check above -- both numbers were cited -- while printing each beside
    #    the wrong name, which is the defect this module is named for.
    if claim.text:
        text = composed_text(claim)
        for c in claim.cites:
            if not isinstance(c.value, (int, float)) or isinstance(c.value,
                                                                  bool):
                continue
            for m in re.finditer(
                    r"%s\s+(\d+\.\d+)" % re.escape(str(c.member)), text):
                printed = m.group(1)
                # Compared at the precision the prose PRINTED. `0.9976` is a
                # faithful rendering of `0.99755`; demanding they be equal to
                # machine precision would flag every display rounding in the
                # report and the check would be dropped within a day. What is
                # forbidden is a number that is not this member's, and a
                # rounding is still this member's.
                nd = len(printed.split(".")[1])
                if round(float(c.value), nd) != float(printed):
                    bad.append(
                        "prose prints %s beside %s, but the claim cites %r "
                        "for it" % (printed, c.member, c.value))
    return bad


def check_all(claims, rows=None):
    """[(claim, [problem])] for every claim that violates the invariant."""
    out = []
    for c in claims:
        problems = check(c, rows)
        if problems:
            out.append((c, problems))
    return out


def raise_on_violation(claims, rows=None, where=""):
    bad = check_all(claims, rows)
    if not bad:
        return
    lines = []
    for c, problems in bad:
        lines.append("  [%s] %s" % (c.kind, c.text[:160]))
        for p in problems:
            lines.append("      - %s" % p)
    raise ClaimViolation(
        "%d claim(s) do not follow from their rows%s:\n%s"
        % (len(bad), (" in " + where) if where else "", "\n".join(lines)))


# --------------------------------------------------------------------------
# rows: the per-member facts a claim is checked against
# --------------------------------------------------------------------------

class RowIndex(dict):
    """`{subject: {member: {constraint: fact}}}` -- facts, per option.

    Keyed by the CONFIGURATION first, because "qdrant's qps verdict" is not
    one fact: a sweep judges eight architectures and qdrant carries a separate
    verdict for each. A flat `{member: {constraint: ...}}` collapses them and
    every claim is then checked against whichever option was written last --
    a check that agrees with the rows by coincidence.

    `None` holds run-level facts, for claims about no particular option.
    """

    def for_claim(self, claim):
        subject = getattr(claim, "subject", None)
        if subject in self:
            return self[subject]
        return self.get(None, {})


def rows_from_options(options):
    """A `RowIndex` from judged options.

    Within one option, members are engines where a verdict is engine-scoped
    and the configuration otherwise, because that is the set the sentences
    quantify over: "both engines", "every configuration".
    """
    rows = RowIndex()
    rows.setdefault(None, {})
    for opt in options or ():
        cfg = getattr(opt, "config", None)
        here = rows.setdefault(cfg, {})
        for v in getattr(opt, "verdicts", ()) or ():
            member = v.engine if v.engine is not None else cfg
            here.setdefault(member, {})[v.constraint] = {
                "value": v.value, "outcome": v.outcome, "source": v.source}
        meas = getattr(opt, "measurement", None) or {}
        for name, value in meas.items():
            here.setdefault(cfg, {}).setdefault(
                name, {"value": value, "outcome": None,
                       "source": "simulate.json:rows[%s].%s" % (cfg, name)})
        if cfg is not None:
            here.setdefault(cfg, {})["outcome"] = {
                "value": None, "outcome": getattr(opt, "outcome", None),
                "source": "report.json:options[%s].judgement.outcome" % cfg}
            # Run-level: a claim with no subject can still name a
            # configuration, and it is the same fact either way.
            rows[None].setdefault(cfg, here[cfg])
    return rows


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------
# One renderer. Every sentence about rows in the report, the decision log, the
# HTML and the console comes through here, and the grep-guard in
# `test_claims.py` fails the suite on any other module that formats an
# outcome, an engine, a verdict or a measured value into a string.

def part(predicate, quantifier, text, scope=(), holds_for=(), cites=(),
         constraint=None):
    """One assertion inside a sentence, with the fragment that states it."""
    return Claim(kind="part", predicate=predicate, quantifier=quantifier,
                 constraint=constraint, scope=tuple(scope),
                 holds_for=tuple(holds_for), cites=tuple(cites), text=text)


def _members(names):
    names = [str(n) for n in names]
    if not names:
        return "nobody"
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def _howmany(n):
    """`Both` is wrong for three. Task 017f."""
    return "Both" if n == 2 else "All %d" % n


def cite_list(cites):
    """`qdrant 200.00 (meets); pgvector 119.10 (fails)` -- each number with
    the verdict that belongs to it, which is the whole point."""
    bits = []
    for c in cites:
        bit = str(c.member)
        if c.value is not None:
            try:
                bit += " %.2f" % float(c.value)
            except (TypeError, ValueError):
                bit += " %s" % c.value
        if c.outcome is not None:
            bit += " (%s)" % c.outcome
        bits.append(bit)
    return "; ".join(bits)


def render(claim):
    """The prose for a Claim. Sets `claim.text` and returns it."""
    fn = _RENDERERS.get(claim.kind)
    if fn is None:
        raise ClaimViolation(
            "no renderer for claim kind %r. Every sentence about rows is "
            "rendered here, so a new kind is a new renderer, not an f-string "
            "somewhere else." % claim.kind)
    claim.text = fn(claim)
    return claim.text


def _r_scope(c):
    names = c.extra.get("constraint_names") or ()
    return ("%d configuration(s) were measured and judged against "
            "%d constraint(s): %s."
            % (c.extra.get("n_options", 0), len(names),
               ", ".join(names) or "none"))


def _r_not_run(c):
    return ("%s was requested but produced no rows, so it is not judged: %s"
            % (c.subject, c.detail))


def _r_fails(c):
    on = " on %s" % c.cites[0].member if c.extra.get("engine_scoped") else ""
    where = (" Measured in environment %s." % c.environment
             if c.environment and c.extra.get("environment_relevant") else "")
    return "%s fails %s%s: %s.%s" % (c.subject, c.constraint, on, c.detail,
                                     where)


def _r_meets_environment(c):
    on = " on %s" % c.cites[0].member if c.extra.get("engine_scoped") else ""
    return ("%s meets %s%s in environment %s: %s."
            % (c.subject, c.constraint, on, c.environment or "unrecorded",
               c.detail))


def _r_meets(c):
    """Each meeting verdict with the engine it belongs to, then -- when the
    option is recorded as meeting only because SOME engine met it -- the
    clause saying so.

    Task 018: `collapse_by_constraint` folds per-engine verdicts permissively,
    and its docstring says that is "only safe because the decision log names
    the engine every time". This is where it names them.
    """
    shown = [cite for cite in c.cites
             if cite.outcome in (None, c.extra.get("meets_outcome", "meets"))]
    listed = "; ".join(
        "%s%s %s" % (cite.constraint or c.constraint,
                     (" on %s" % cite.member
                      if cite.member is not None and cite.member != c.subject
                      else ""),
                     cite.reason)
        for cite in shown)
    head = "%s meets every constraint that could be checked: %s." % (
        c.subject, listed)
    tail = c.extra.get("not_on_every_engine") or ""
    # Two assertions quantifying over two different sets. The first is
    # universal over the CONSTRAINTS that could be checked -- which is what
    # "every constraint that could be checked" says, and it is true by
    # construction because `Option.outcome` is `meets` only when every
    # collapsed constraint meets. The second is a denial about the ENGINES.
    checked = tuple(dict.fromkeys(
        (cite.constraint or c.constraint) for cite in shown))
    # Keyed by constraint, because that is the set this half quantifies over.
    by_constraint = tuple(
        Cite(member=(cite.constraint or c.constraint), value=cite.value,
             outcome=cite.outcome, constraint=(cite.constraint or c.constraint),
             source=cite.source, reason=cite.reason)
        for cite in shown)
    c.parts = (
        part("meets every constraint that could be checked", UNIVERSAL, head,
             scope=checked, holds_for=checked, cites=by_constraint),
    ) + ((part("is not true of every engine", NEGATION, tail.strip(),
               scope=c.scope, holds_for=c.holds_for,
               cites=c.cites),) if tail.strip() else ())
    return head + tail


def _r_indistinguishable(c):
    vals = "; ".join("%s %.4f" % (cite.member, float(cite.value))
                     for cite in c.cites)
    overall = "; ".join("%s %s" % (cite.member, cite.outcome)
                        for cite in c.cites)
    head = ("These options are indistinguishable on recall: %s. Their recall "
            "differs by less than the calibration tolerance (%s), which is "
            "what this project can currently defend, so choosing between them "
            "on recall would be reading noise. They are separated only where "
            "they differ measurably." % (vals, c.extra.get("tolerance")))
    tail = ("Overall: %s -- indistinguishable on recall is not "
            "indistinguishable overall." % overall)
    # Universal over the group on recall; then a denial that the same holds
    # overall, with each option's own outcome beside it. The denial is the
    # point: 013's report invited a reader to treat the runner-up as equally
    # supported because the first half was true.
    c.parts = (
        part("are indistinguishable on recall", UNIVERSAL, head,
             scope=c.scope, holds_for=c.holds_for, cites=c.cites,
             constraint=c.constraint),
        part("indistinguishable on recall is not indistinguishable overall",
             NEGATION, tail, scope=c.scope, holds_for=(), cites=c.cites),
    )
    return "%s %s" % (head, tail)


def _r_engine_comparison(c):
    """Three assertions in one sentence, and they quantify differently.

    Which is why `{best.outcome}` survived review: "X is the better of two"
    and "both carry meets" sit side by side, the first is existential and true
    and the second was universal and false, and nothing in a string can tell
    them apart. Here each is a part with its own quantifier and its own set.
    """
    best = c.extra["best"]
    best_cite = next(x for x in c.cites if x.member == best)
    others = cite_list([x for x in c.cites if x.member != best])
    members = tuple(x.member for x in c.cites)
    uniform = len(set(x.outcome for x in c.cites)) == 1

    head = ("%s: on %s, %s is the better of %d engines measured in "
            "environment %s -- %s against %s."
            % (c.subject, c.constraint, best, len(c.cites),
               c.environment or "unrecorded", cite_list([best_cite]), others))
    measured = ("%s were measured on the same sample, on the same host, "
                "sequentially." % _howmany(len(c.cites)))
    if uniform:
        # "All N carry", never "Both carry": the clauses count differently on
        # purpose. "Both were measured" reads naturally for two; "All 2 carry
        # fails" keeps the number so a reader sees the set it covers.
        verdicts = "All %d carry %s against the constraint." % (
            len(c.cites), best_cite.outcome)
        verdict_part = part("carry the same outcome", UNIVERSAL, verdicts,
                            scope=members, holds_for=members, cites=c.cites,
                            constraint=c.constraint)
    else:
        verdicts = ("The verdicts differ -- a better number here is not the "
                    "same as a passing one.")
        verdict_part = part("the verdicts differ", NEGATION, verdicts,
                            scope=members, holds_for=(), cites=c.cites,
                            constraint=c.constraint)

    c.parts = (
        part("is the better of the engines measured", EXISTENTIAL, head,
             scope=members, holds_for=(best,), cites=c.cites,
             constraint=c.constraint),
        part("were measured on the same sample, host and order", UNIVERSAL,
             measured, scope=members, holds_for=members, cites=c.cites),
        verdict_part,
    )
    return ("%s %s %s %s" % (head, measured, verdicts, c.detail)).rstrip()


def _r_no_engine_comparison(c):
    return ("%s: %s was not compared across engines because fewer than two "
            "engines produced a value -- %s. A comparison here would be "
            "between a number and an absence"
            % (c.subject, c.constraint,
               ", ".join("%s (%s)" % (x.member, x.outcome) for x in c.cites)))


def _r_engines_meeting(c):
    """Universal over the constraints, existential over the engines.

    "meets every engine-scoped constraint" ranges over constraints; "on:
    qdrant" ranges over engines and names the subset. One quantifier cannot
    be right about both, so there are two parts.
    """
    # Cut the sentence where the quantifier changes, not where the full stop
    # is. The first fragment ranges over constraints; the second names the
    # engines, and an existential that does not name its members is the
    # defect this module exists to refuse.
    universal_half = "%s meets every engine-scoped constraint" % c.subject
    existential_half = ("on: %s. Deploying it means choosing one of those; "
                        "the others were measured and did not clear"
                        % ", ".join(c.holds_for))
    constraints = tuple(c.extra.get("engine_scoped_constraints") or ())
    by_constraint = tuple(
        Cite(member=name, outcome=None, constraint=name,
             source="report.json:options[*].judgement.engines_meeting")
        for name in constraints)
    c.parts = (
        part("meets every engine-scoped constraint", UNIVERSAL,
             universal_half, scope=constraints, holds_for=constraints,
             cites=by_constraint),
        part("holds on these engines and not the others", EXISTENTIAL,
             existential_half, scope=c.scope, holds_for=c.holds_for,
             cites=c.cites),
    )
    return "%s %s" % (universal_half, existential_half)


def _r_recommendation(c):
    if c.subject is None:
        # A denial, and it is checked as one. "No option meets every
        # constraint" is not a universal claim about options with the word
        # "no" attached; it is the denial of one, and 017f shipped a guard
        # that could not tell the difference.
        text = ("No option meets every constraint, so nothing is recommended. "
                "Recommending an option whose constraints could not all be "
                "checked would be rounding couldn't-check up to a verdict.")
        c.parts = (part("no option meets every constraint", NEGATION, text,
                        scope=c.scope, holds_for=()),)
        return text
    margins = c.extra.get("margins") or []
    head = "Recommended: %s. It meets every constraint that could be checked" \
           % c.subject
    tail = (", and was ranked first by: fewest constraints at margin (%d%s), "
            "then lowest storage amplification (%.2fx), then lowest fan-out "
            "(%.0f)."
            % (len(margins), (": " + ", ".join(margins)) if margins else "",
               c.extra.get("storage") or 0.0, c.extra.get("fanout") or 0.0))
    checked = tuple(c.extra.get("checked_constraints") or ())
    c.parts = (
        part("meets every constraint that could be checked", UNIVERSAL, head,
             scope=checked, holds_for=checked,
             cites=tuple(Cite(member=n, constraint=n,
                              source="report.json:options[%s].judgement"
                                     % c.subject) for n in checked)),
        part("was ranked first by the stated tie-breaks", NONE, tail),
    )
    return head + tail


def _r_to_resolve(c):
    return c.detail


def _r_analogy(c):
    return c.detail


def _r_capacity(c):
    return c.detail


def _r_qps_max(c):
    cite = c.cites[0]
    who = "%s: " % cite.member if cite.member else ""
    return ("%s%.1f qps at concurrency %s (p99 %.1f ms). Ramp stopped because "
            "%s. %s"
            % (who, float(cite.value), c.extra.get("concurrency"),
               c.extra.get("p99") or 0.0, c.extra.get("stopped", ""), c.detail))


# --------------------------------------------------------------------------
# the proposal card (task 028)
# --------------------------------------------------------------------------
# A card's sentences are about rows exactly as a report's are -- the same
# invariant, the same renderer, the same oracle. They live here because this
# is the one module allowed to interpolate an outcome or a measured value into
# a string, and a card that rendered its own prose would be the presentation
# layer without an oracle all over again.
#
# The verdict words differ from the report's: a prediction held or did not
# hold, where a configuration meets or fails a constraint. They are kept
# apart deliberately -- a proposal is judged on a difference between two
# configurations, never against the report's absolute thresholds.

def _r_proposal_change(c):
    return ("Policy: %s. Measured as %s on %s vectors and %s queries of %s, "
            "seed %s, against exact k-NN ground truth for that sample."
            % (c.extra.get("changes"), c.subject,
               c.extra.get("n_base"), c.extra.get("n_queries"),
               c.extra.get("run"), c.extra.get("seed")))


def _r_proposal_outcome(c):
    head = {"held": "The prediction held for %s.",
            "did_not_hold": "The prediction did not hold for %s.",
            "couldnt_check": "The prediction could not be checked for %s."}
    line = head.get(c.asserts_outcome or "", "%s")  % c.subject
    return (line + " " + c.detail).strip() if c.detail else line


# `rises` is how a prediction names a direction; `rise` is how a sentence
# says it after "predicted to".
DIRECTION_VERB = {"rises": "rise", "falls": "fall"}


def _r_proposal_metric(c):
    direction = c.extra.get("direction")
    return ("%s %s by %s, from %s to %s; predicted to %s by at least %s. "
            "This one %s."
            % (c.constraint, direction, c.extra.get("delta"),
               c.extra.get("before"), c.extra.get("after"),
               DIRECTION_VERB.get(direction, direction),
               c.extra.get("threshold"), outcome_label(c.asserts_outcome)))


def _r_proposal_budget(c):
    return ("Side-effect budget: %s is %s on the changed configuration, "
            "bounded to %s %s. This one %s."
            % (c.constraint, c.extra.get("after"), c.extra.get("bound_phrase"),
               c.extra.get("bound"), outcome_label(c.asserts_outcome)))


def _r_proposal_unchecked(c):
    """A predicted metric with no measurement behind it.

    Its own sentence rather than the metric sentence with blanks in it: a row
    that reads "rises by no measurement" is a sentence pretending to be a
    result. `detail` is the run's own account of why, and what would settle it.
    """
    return ("%s: %s. %s" % (c.constraint, outcome_label(c.asserts_outcome),
                            c.detail)).strip()


def _r_proposal_baseline(c):
    return ("The baseline was not re-run: %s is the row %s already held "
            "(file %s, row %s), measured %s."
            % (c.subject, c.extra.get("file"), c.extra.get("file_sha256"),
               c.extra.get("row_sha256"), c.extra.get("measured_at")))


def _r_proposal_calibration(c):
    return ("Judged at calibration tolerance %s. %s"
            % (c.extra.get("tolerance"), c.detail)).strip()


def _r_proposal_limits(c):
    """The card's limits, in the plainest words there are.

    Those words are the ones a card may never use about itself -- good,
    recommended, deployed, at full scale -- which is why `card.forbidden_in`
    exempts this one sentence and nothing else. A rule that punished the
    caveat for naming what it rules out would be answered by deleting the
    caveat.
    """
    return ("This card reports one run of one policy on one sample: %s "
            "vectors and %s queries drawn from %s, judged against exact k-NN "
            "ground truth for that sample. It says what the measured "
            "difference was. It does not say the change is good, or "
            "recommended, or that it should be deployed; it says nothing "
            "about any other corpus; and it does not say this result would "
            "hold at full scale."
            % (c.extra.get("n_base"), c.extra.get("n_queries"),
               c.extra.get("run")))


_RENDERERS = {
    "proposal_change": _r_proposal_change,
    "proposal_outcome": _r_proposal_outcome,
    "proposal_metric": _r_proposal_metric,
    "proposal_budget": _r_proposal_budget,
    "proposal_unchecked": _r_proposal_unchecked,
    "proposal_baseline": _r_proposal_baseline,
    "proposal_calibration": _r_proposal_calibration,
    "proposal_limits": _r_proposal_limits,
    "scope": _r_scope,
    "not_run": _r_not_run,
    "fails": _r_fails,
    "meets_environment": _r_meets_environment,
    "meets": _r_meets,
    "indistinguishable": _r_indistinguishable,
    "engine_comparison": _r_engine_comparison,
    "no_engine_comparison": _r_no_engine_comparison,
    "engines_meeting": _r_engines_meeting,
    "recommendation": _r_recommendation,
    "to_resolve": _r_to_resolve,
    "analogy": _r_analogy,
    "capacity": _r_capacity,
    "qps_max": _r_qps_max,
}

RENDERED_KINDS = tuple(sorted(_RENDERERS))


# --------------------------------------------------------------------------
# the surfaces that are not sentences: cells, rows, console lines
# --------------------------------------------------------------------------
# Task 019. A table cell and a console row assert exactly what a sentence
# does -- 017e's defect was a cell -- so they are rendered here too, and the
# HTML and the console receive strings rather than verdicts.

# `did_not_hold` is a proposal card's outcome (task 028); the report has no
# such verdict and never reads this entry.
OUTCOME_LABELS = {"couldnt_check": "couldn't-check",
                  "did_not_hold": "did not hold"}


def outcome_label(outcome, html=False):
    """`couldnt_check` is written `couldn't-check` for a reader."""
    text = OUTCOME_LABELS.get(outcome, outcome)
    return text.replace("'", "&#39;") if html else text


def not_on_every_engine(opt_verdicts, meets="meets"):
    """The clause the `meets` sentence needs when an engine failed.

    `collapse_by_constraint` folds per-engine verdicts permissively -- a
    constraint `meets` when at least one engine meets it -- and its docstring
    says that is "only safe because the decision log names the engine every
    time". This is the naming.
    """
    by_constraint = {}
    for v in opt_verdicts:
        if v.engine is None:
            continue
        by_constraint.setdefault(v.constraint, []).append(v)
    bad = {}
    for name, group in by_constraint.items():
        if any(v.outcome == meets for v in group):
            others = [v for v in group if v.outcome != meets]
            if others:
                bad[name] = others
    if not bad:
        return ""
    bits = "; ".join(
        "%s does not on %s"
        % (name, ", ".join("%s (%s)" % (v.engine, v.outcome)
                           for v in sorted(group, key=lambda v: str(v.engine))))
        for name, group in sorted(bad.items()))
    return (" This is not true of every engine measured: %s. `meets` for a "
            "configuration means it meets on at least one engine measured, "
            "not on all of them" % bits)


def verdict_cell(group, tokens, couldnt_check="couldnt_check",
                 collapse=None):
    """The presentation of one constraint's verdicts for one configuration.

    Returns plain strings: the collapsed outcome and its CSS token, a title,
    and one entry per engine with its own outcome. **Task 017e's defect was
    here** -- the cell rendered the first verdict, so a configuration that met
    the budget on Qdrant and missed it on pgvector by forty times showed one
    flat green `meets` and the failing number was nowhere on the page.
    """
    collapsed = collapse(group) if collapse else group[0].outcome
    title = "\n".join(
        (("%s: " % v.engine) if v.engine else "")
        + "%s\nsource: %s" % (v.reason, v.source) for v in group)
    single = len(group) == 1 and group[0].engine is None
    return {
        "outcome": collapsed,
        "token": tokens[collapsed],
        "label": outcome_label(collapsed, html=True),
        "title": title,
        "source": group[0].source if single else "",
        "per_engine": ([] if single else [
            {"text": "%s %s" % (v.engine or "unattributed",
                                outcome_label(v.outcome, html=True)),
             "token": tokens[v.outcome]} for v in group]),
    }


def recommendation_rows(verdicts, tokens):
    """One row per verdict on the recommended option, each naming its engine.

    Two engines produce two `latency_p95` rows; without the engine they read
    as one constraint answered twice and contradictorily.
    """
    return [{"token": tokens[v.outcome], "constraint": v.constraint,
             "engine": (str(v.engine) if v.engine else ""),
             "reason": v.reason}
            for v in verdicts]


def option_row(opt):
    """The console row for one option: config, outcome, per-verdict bits."""
    return {
        "config": opt.config,
        "outcome": opt.outcome,
        "bits": " ".join(
            "%s%s=%s" % (v.constraint,
                         ("@" + str(v.engine)) if v.engine else "",
                         v.outcome)
            for v in opt.verdicts),
        "engines_meeting": list(opt.engines_meeting or ()),
    }


def runner_up_lines(recommended, options, meets="meets",
                    couldnt_check="couldnt_check"):
    """"indistinguishable on recall from ..." -- with what it costs.

    Naming an alternative beside a recommendation reads as an endorsement, so
    the line says what the alternative's overall outcome is. On the arxiv-150k
    report the runner-up is `couldnt_check`: it was not the configuration the
    engine was built as, so its latency and throughput were never measured.
    The recall half of the claim stands; what was missing is everything the
    comparison does not cover.
    """
    if not recommended or not recommended.indistinguishable_from:
        return []
    by_config = {o.config: o for o in options or []}
    out = ["    indistinguishable on recall from: "
           + ", ".join(recommended.indistinguishable_from)]
    for cfg in recommended.indistinguishable_from:
        opt = by_config.get(cfg)
        if opt is None:
            continue
        if opt.outcome == meets:
            out.append("      %s: meets every constraint that could be "
                       "checked" % cfg)
            continue
        unchecked = [v.constraint for v in opt.verdicts
                     if v.outcome == couldnt_check]
        failed = [v.constraint for v in opt.verdicts if v.outcome == "fails"]
        bits = []
        if failed:
            bits.append("fails " + ", ".join(failed))
        if unchecked:
            bits.append("could not be checked on " + ", ".join(unchecked))
        out.append("      %s: %s%s. Indistinguishable on recall is not "
                   "indistinguishable overall."
                   % (cfg, opt.outcome,
                      (" -- " + "; ".join(bits)) if bits else ""))
    return out


def how_to_resolve(name, verdict, verify_info):
    """What is missing. Specific, not generic."""
    reason = verdict.reason
    if name == "latency_p95":
        if "no verify run" in reason:
            return ("To decide latency_p95: run `oneground verify` against a "
                    "real engine in the environment the constraint targets. "
                    "Latency is never taken from simulation.")
        if "could not attribute" in reason:
            env = (verify_info or {}).get("platform", "this machine")
            return ("To decide latency_p95: re-run `oneground verify` where "
                    "the round trip to the engine is small relative to the "
                    "query. On " + env + " the baseline RTT was a large "
                    "fraction of the query p95, so the number measured the "
                    "path rather than the engine. A pod session with the "
                    "client and engine in the same environment is the way to "
                    "settle it (task 011).")
        if "constraint targets" in reason:
            return ("To decide latency_p95: measure in the environment the "
                    "constraint names. " + reason + ".")
        return "To decide latency_p95: %s." % reason
    if name == "monthly_budget":
        return ("To decide monthly_budget: a cost model with error bands is "
                "not in this build (task 011). Nothing here estimates cost, "
                "because a confident number from list prices would be "
                "fiction.")
    return "To decide %s: %s." % (name, reason)
