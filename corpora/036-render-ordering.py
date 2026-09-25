"""The ordering and the truncation confound, in one table.

The confound is not a footnote to the ordering, it is a column of it. If a
corpus is measured on half of each record under one model and all of it under
the others, that is a candidate explanation for where it lands -- and a reader
has to meet it at the same time as the number, not after.

So this renders one row per (corpus, model) carrying the crispness AND what
the model actually read, and then answers three questions in order:

  1. does each model reproduce the published ordering?
  2. is the ordering the same under all three models?
  3. if it holds under some and not others -- does it hold only under the
     models that truncate least? A "stable ordering" that is stable only
     where nothing was cut is not a stable ordering, and saying so is the
     point of this script.
"""
import json
import os
import sys

RESULTS = os.environ.get("ONEGROUND_036_OUT",
                         "tasks/scratch/036-ordering-results.json")
TRUNC = "tasks/scratch/036-truncation-results.json"
PUBLISHED = {"sec-filings-10k": 0.107347, "arxiv-150k": 0.036273,
             "stackexchange-150k": 0.0115}
# A truncation rate this far above the lowest makes a model a "truncating"
# one for the conditional-stability question. Same threshold the artifact
# uses (embed/compare.TRUNCATION_CONFOUND_DELTA).
CONFOUND_DELTA = 0.05


def short(m):
    return m.split("/")[-1]


def ordering(values):
    """Corpora, crispest first."""
    return tuple(c for c, _ in sorted(values.items(), key=lambda kv: -kv[1]))


def main():
    if not os.path.exists(RESULTS):
        print("no results yet at %s" % RESULTS)
        return 1
    r = json.load(open(RESULTS, encoding="utf-8"))
    design, cells = r.get("design", {}), r.get("cells", {})
    trunc = (json.load(open(TRUNC, encoding="utf-8"))
             if os.path.exists(TRUNC) else {})

    models = design.get("models", [])
    # `design["corpora"]` (task 065) is what THIS run intended to measure --
    # older results have no such key, and for those every published corpus
    # is still assumed intended, which is what "incomplete" meant before this
    # field existed.
    intended = design.get("corpora") or list(PUBLISHED)
    corpora = [c for c in intended if c in cells]
    skipped = [c for c in PUBLISHED if c not in intended]
    done = sum(len(v) for v in cells.values())
    print("design: N=%s  centroids=%s  seed=%s  %s"
          % (design.get("n_base"), design.get("centroids"),
             design.get("seed"),
             "FULL SIZE" if design.get("full_size") else "subsample"))
    print("cells complete: %d of %d" % (done, len(intended) * len(models)))
    if skipped:
        print("corpora not run this session: %s (published value only, "
              "not settled by this run)" % ", ".join(skipped))
    print()

    print("CRISPNESS AND WHAT THE MODEL ACTUALLY READ")
    print("  %-22s %-18s %10s %9s %9s %11s"
          % ("corpus", "model", "crispness", "max_seq", "mean tok", "truncated"))
    print("  " + "-" * 84)
    unresolved = []
    for corpus in sorted(corpora, key=lambda c: -PUBLISHED[c]):
        for m in models:
            cell = cells.get(corpus, {}).get(m)
            if not cell:
                continue
            t = (trunc.get(corpus) or {}).get(m) or {}
            mean_tok = t.get("mean_tokens")
            print("  %-22s %-18s %10.4f %9s %9s %11s"
                  % (corpus, short(m), cell["boundary_crispness"],
                     cell.get("max_seq_length", t.get("max_seq_length", "-")),
                     ("%.1f" % mean_tok) if mean_tok else "-",
                     ("%.1f%%" % (100 * t["truncated_fraction"]))
                     if "truncated_fraction" in t else "couldn't-check"))
            # Task 044: a count near zero is not thereby a corpus with no
            # boundary structure -- it can also be a threshold that has left
            # this embedding's distribution entirely. `crispness_reading`
            # says which, when the ordering experiment was wired to compute
            # it; older results (subsample, pre-044) do not carry it, and
            # that absence is reported rather than assumed to mean "fine."
            cr = cell.get("crispness_reading")
            if cr is None:
                print("  %-22s %-18s   no crispness_reading in this result "
                      "-- computed before the reading() wiring, or the "
                      "session that produced it bypassed it"
                      % ("", ""))
                continue
            if not cr.get("resolvable", True):
                unresolved.append((corpus, short(m)))
                print("  %-22s %-18s   COULDN'T-CHECK: %s"
                      % ("", "", cr["why"]))
            tr = cr.get("transfer", {})
            if tr.get("outcome") == "couldnt_check":
                print("  %-22s %-18s   transfer: %s"
                      % ("", "", tr["note"]))
            elif "outside_published_range" in tr:
                print("  %-22s %-18s   transfer: %s (threshold at the %.2fth "
                      "percentile here; published span %.1f-%.1f)"
                      % ("", "",
                         "OUTSIDE published band" if tr["outside_published_range"]
                         else "inside published band",
                         cr["threshold_percentile"], *tr["published_range"]))
        print()
    if unresolved:
        print("  NOTE: %d cell(s) report a count not distinguishable from "
              "zero -- read as couldn't-check, not as zero boundary "
              "structure: %s"
              % (len(unresolved),
                 ", ".join("%s/%s" % (c, m) for c, m in unresolved)))
        print()

    print("PUBLISHED, full size, 256 centroids, bge-base-en-v1.5")
    for c, v in sorted(PUBLISHED.items(), key=lambda kv: -kv[1]):
        print("   %-22s %.4f" % (c, v))
    print("   ordering (all 3 published corpora): %s" % " > ".join(
        short(c) for c in ordering(PUBLISHED)))
    if skipped:
        print("   this session only measured: %s"
              % ", ".join(short(c) for c in intended))
    print()

    # Everything below settles the ordering among the corpora THIS session
    # ran, not the full published three -- `skipped` corpora keep their
    # published position as context above, never as a measured one here.
    published_subset = {c: v for c, v in PUBLISHED.items() if c in intended}

    print("ORDERING PER MODEL")
    orderings, rates = {}, {}
    for m in models:
        vals = {c: cells[c][m]["boundary_crispness"]
                for c in corpora if m in cells.get(c, {})}
        if len(vals) < len(intended):
            print("   %-18s incomplete (%d of %d corpora)"
                  % (short(m), len(vals), len(intended)))
            continue
        orderings[m] = ordering(vals)
        worst = max((trunc.get(c, {}).get(m, {}).get("truncated_fraction", 0.0)
                     for c in corpora), default=0.0)
        rates[m] = worst
        print("   %-18s %-56s (worst truncation %.1f%%)"
              % (short(m), " > ".join(short(c) for c in orderings[m]),
                 100 * worst))
    print()

    if len(orderings) < len(models):
        print("VERDICT: incomplete. %d of %d models measured on all corpora."
              % (len(orderings), len(models)))
        return 0

    published_order = ordering(published_subset)
    agree = {m: o == published_order for m, o in orderings.items()}
    distinct = set(orderings.values())

    print("VERDICT")
    if len(distinct) == 1 and all(agree.values()):
        print("   The ordering is the SAME under all three models, and it is")
        print("   the published one: %s"
              % " > ".join(short(c) for c in published_order))
        lowest = min(rates.values())
        heavy = [m for m, v in rates.items() if v - lowest > CONFOUND_DELTA]
        if heavy:
            print()
            print("   AND IT HOLDS UNDER THE TRUNCATING MODELS TOO: %s "
                  "truncate" % ", ".join(short(m) for m in heavy))
            print("   materially more than the others and still order the")
            print("   corpora the same way, which is the stronger result --")
            print("   the ordering survived reading less of the corpus.")
        else:
            print()
            print("   No model truncates materially more than another here,")
            print("   so this says nothing about whether the ordering would")
            print("   survive truncation. It was not tested.")
    elif len(distinct) == 1:
        print("   All three models agree with each other and DISAGREE with")
        print("   the published ordering. That points at the subsample or the")
        print("   centroid count, not at the models.")
    else:
        print("   THE ORDERING IS NOT STABLE ACROSS MODELS.")
        for m, o in orderings.items():
            print("     %-18s %s%s" % (short(m),
                                       " > ".join(short(c) for c in o),
                                       "" if agree[m] else "   <- differs"))
        lowest = min(rates.values())
        held = [m for m in orderings if agree[m]]
        heavy_held = [m for m in held if rates[m] - lowest > CONFOUND_DELTA]
        if held and not heavy_held:
            print()
            print("   AND THE ORDERING HOLDS ONLY UNDER THE MODELS THAT")
            print("   TRUNCATE LEAST. That is not a stable ordering: it is an")
            print("   ordering that survives where the corpus was read whole")
            print("   and fails where it was not, and the truncation is a")
            print("   candidate explanation for both halves.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
