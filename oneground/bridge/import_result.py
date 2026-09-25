"""The VectorDBBench importer. `docs/BRIDGE.md` §4, §8.

Reads a result file VectorDBBench 2.0.0 already wrote -- this module does
not run, install or vendor VectorDBBench (`docs/BRIDGE.md` §5). The schema
below was read from `vectordb-bench==2.0.0`'s own source
(`vectordb_bench/models.py`'s `TestResult`/`CaseResult`/`Metric`,
`vectordb_bench/interface.py::_async_task_v2`, and the real result files
under `vectordb_bench/results/*/result_*.json`), the same primary-source
method the rest of this position paper uses, because §4 named what comes
back without ever having read the file it comes back in.

**Two things §4 claimed that the primary source does not support, corrected
here rather than worked around** (`docs/BRIDGE.md` §4 carries the same
correction):

1. **No composite score is ever in a per-case result.** VectorDBBench's
   composite ranking is computed downstream, across every provider's file
   at once, by `results/getLeaderboardData.py` and the frontend scoring
   code -- never persisted beside the raw numbers this module reads.
   "Never import the composite" is satisfied by scope, not by a
   field-level filter: this module reads one provider's
   `results/<Provider>/result_*.json` and nothing that name matches; the
   file it reads never contains a composite score to exclude, and a
   leaderboard file is simply never opened.
2. **A failed or timed-out case carries no reason string and no captured
   timeout duration.** `interface.py::_async_task_v2` catches the
   exception, logs it, and discards it -- only a `label` survives to the
   file: `ResultLabel.FAILED` (`"x"`) for any exception, `ResultLabel.
   OUTOFRANGE` (`"?"`) specifically for a caught `LoadTimeoutError` or
   `PerformanceTimeoutError`. This module reports which of the two
   occurred and, where the case's own configuration declares a
   concurrency-search timeout (`case_config.concurrency_search_config.
   concurrency_timeout`), names it as the *configured* value for that
   stage -- never as *the* timeout that fired, which no field in the file
   distinguishes a load-stage timeout from a search-stage one to say.

**Two of `docs/BRIDGE.md` §4's four row labels are not recorded by
VectorDBBench's own result file at all.** `engine` (`task_config.db`) and
`engine_version` (`task_config.db_config.version`, when the config
declares one) are present. Neither VectorDBBench's own package version nor
the host it ran on appears anywhere in `TestResult`, `CaseResult` or
`TaskConfig` in the real files this was checked against. Declared `null`
with a stated reason, the same shape `docs/PROPOSALS.md` §2.1 uses for an
unreported model version -- not fabricated, not silently dropped.
"""

import json
import os

from ..comparability import (COMPARABLE, DIFFERS, MEASURED_KEYS,
                             NOT_COMPARABLE, Provenance, SAME, UNKNOWN)

RESULT_LABEL_NORMAL = ":)"
RESULT_LABEL_FAILED = "x"
RESULT_LABEL_OUTOFRANGE = "?"

COULDNT_CHECK = "couldnt_check"
MEASURED = "measured"

#: `docs/BRIDGE.md` §4's raw per-case numbers, read by name from
#: `CaseResult.metrics` -- never the whole dict, which is how a field added
#: to `Metric` later (VectorDBBench's own, not this project's) would import
#: itself without anyone deciding it should.
RAW_CASE_FIELDS = ("qps", "serial_latency_p50", "serial_latency_p95",
                   "serial_latency_p99", "recall", "ndcg",
                   "load_duration", "insert_duration", "optimize_duration",
                   "max_load_count")

#: Not recorded by VectorDBBench's own result file, per this module's own
#: docstring. Declared here once rather than as two ad hoc strings, so a
#: reader sees both reasons share one sentence.
_NOT_RECORDED = ("not recorded by VectorDBBench's own result file, and not "
                 "obtainable without running the harness, which this "
                 "importer does not do")


class BridgeImportError(ValueError):
    """A result file, or a card, could not be honestly imported."""


class TableConstructionError(ValueError):
    """Two rows whose provenance disagrees cannot be placed in one table.

    `docs/BRIDGE.md` §4's table rule, refused at construction on 026's and
    034's pattern -- there is no path through `assemble_table` that
    returns a table built from rows it has not itself compared.
    """


def _failure_reason(label):
    if label == RESULT_LABEL_OUTOFRANGE:
        return ("a load or search stage exceeded its configured timeout; "
                "VectorDBBench caught a LoadTimeoutError or "
                "PerformanceTimeoutError for this case")
    if label == RESULT_LABEL_FAILED:
        return ("the case raised an exception VectorDBBench did not "
                "classify as a timeout; the exception itself is not in "
                "the result file, only in that run's own log, which this "
                "importer never sees")
    return f"unrecognised result label {label!r}"


def _configured_concurrency_timeout(task_config):
    case_config = task_config.get("case_config") or {}
    conc = case_config.get("concurrency_search_config") or {}
    return conc.get("concurrency_timeout")


def import_case(case_result):
    """One `CaseResult` dict, as VectorDBBench's own JSON writes it, to one
    row: raw numbers on success, `couldnt_check` on failure or timeout.
    Never a composite score -- `case_result` does not carry one to exclude.
    """
    label = case_result.get("label")
    task_config = case_result.get("task_config") or {}
    row = {
        "engine": task_config.get("db"),
        "engine_version": (task_config.get("db_config") or {}).get("version"),
        "vectordbbench_version": None,
        "vectordbbench_version_reason": _NOT_RECORDED,
        "host": None,
        "host_reason": _NOT_RECORDED,
        "label": label,
    }

    if label != RESULT_LABEL_NORMAL:
        row["outcome"] = COULDNT_CHECK
        row["reason"] = _failure_reason(label)
        row["configured_concurrency_timeout"] = \
            _configured_concurrency_timeout(task_config)
        return row

    metrics = case_result.get("metrics") or {}
    row["outcome"] = MEASURED
    row["metrics"] = {k: metrics.get(k) for k in RAW_CASE_FIELDS}
    return row


def read_result_file(path):
    """Every case in one VectorDBBench result file, imported.

    Refuses a file this importer cannot trust the shape of, rather than
    guessing at missing keys -- the same refusal the exporter makes for a
    query id it cannot cast (`docs/BRIDGE.md` §3.1).
    """
    if not os.path.exists(path):
        raise BridgeImportError(f"{path}: no such file")
    with open(path, encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise BridgeImportError(f"{path}: not valid JSON ({e})") from None

    for key in ("run_id", "results"):
        if key not in data:
            raise BridgeImportError(
                f"{path}: missing {key!r} -- not shaped like a "
                "VectorDBBench TestResult")

    return {"run_id": data["run_id"], "task_label": data.get("task_label"),
           "source_file": path,
           "cases": [import_case(c) for c in data["results"]]}


def provenance_from_card(card):
    """The `Provenance` a bridge-imported row carries, from the exporter's
    own card (`oneground.bridge.export`'s `vdbbench_card.json`).

    The ground truth is `neighbors.parquet`'s own digest -- the exact file
    VectorDBBench graded against, not a description of it. The query
    subset is the seeded receipt task 051 added specifically to close
    `docs/BRIDGE.md` §4's "one ingredient this paper needs is still
    absent" gap -- this is the first place that receipt is read rather
    than only written, so `query_subset` need not be declared absent here
    the way `oneground.comparability.provenance_of` still declares it for
    oneground's own rows.
    """
    files = card.get("files") or {}
    gt_file = card.get("gt_file", "neighbors.parquet")
    if gt_file not in files:
        raise BridgeImportError(
            f"the card does not carry a digest for {gt_file!r} -- it is "
            "not the card `export()` wrote, or the export did not finish")
    query_subset = card.get("query_subset") or {}
    requirements = card.get("requirements_file") or {}
    return Provenance(
        measured={"sample": requirements.get("sha256"),
                 "ground_truth": files[gt_file],
                 "query_subset": query_subset.get("sha256")},
        measuring={}, run=None, workdir=None)


def _measured_verdict(left, right):
    """`docs/BRIDGE.md` §4's own rule, applied directly: *"A row belongs
    to the ground truth, the query subset and the corpus digest it was
    measured against. Two rows may share a table only when all three
    match."* Three keys, stated in the blockquote and nowhere else.

    Deliberately **not** `oneground.comparability.rows_may_share_a_table`,
    which also requires the two rows' `measuring` facts (oneground's own
    code, libraries, platform) to agree. A VectorDBBench row was not
    measured by oneground at all -- it has no `measuring` half to carry --
    so that function's `comparable` branch is structurally unreachable for
    any table a bridge row is in: `measuring`'s keys read `None` on the
    bridge side and score `unknown` regardless of what the `measured`
    triple says, which would refuse every bridge table on an axis §4
    never asked about. This reimplements only the three keys the position
    paper's rule actually names, using the same `MEASURED_KEYS` tuple and
    the same three-valued comparison `oneground.comparability` uses, so
    the *meaning* of same/differs/unknown is not a second definition --
    only which keys are asked about differs, on purpose.
    """
    findings = []
    for key in MEASURED_KEYS:
        a, b = left.measured.get(key), right.measured.get(key)
        state = UNKNOWN if a is None or b is None else (
            SAME if a == b else DIFFERS)
        findings.append((key, state, a, b))
    if any(state == DIFFERS for _, state, _, _ in findings):
        return NOT_COMPARABLE, findings
    if any(state == UNKNOWN for _, state, _, _ in findings):
        return "couldnt_check", findings
    return COMPARABLE, findings


def assemble_table(rows_with_provenance):
    """Rows, each paired with the `Provenance` it was measured under, to
    one table -- or a `TableConstructionError`.

    Structural rather than a check a caller could skip: there is no
    returned table this function has not itself verified every row of
    against the first, so a mismatched row cannot reach a caller by way of
    a construction path that forgot to ask. `couldnt_check` is refused
    here exactly as `not_comparable` is -- a table a reader cannot be
    told is comparable is not one this function will build.
    """
    rows_with_provenance = list(rows_with_provenance)
    if len(rows_with_provenance) < 2:
        return [row for row, _ in rows_with_provenance]
    _, base_prov = rows_with_provenance[0]
    for row, prov in rows_with_provenance[1:]:
        verdict, findings = _measured_verdict(base_prov, prov)
        if verdict != COMPARABLE:
            disagreement = next(
                (f"{k} ({a!r} vs {b!r})" for k, s, a, b in findings
                 if s != SAME), "an ingredient")
            raise TableConstructionError(
                f"{disagreement} -- docs/BRIDGE.md §4's table rule "
                f"(verdict: {verdict})")
    return [row for row, _ in rows_with_provenance]
