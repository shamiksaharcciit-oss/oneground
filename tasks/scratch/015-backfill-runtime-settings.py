"""015: backfill engine runtime settings into the pod run's verify_info.json.

The adapters now read these back from the engine on every run. Session
20260911-181410 finished before that existed and its pod is terminated, so
nothing can be read back from it now.

What CAN be stated is what the launch configuration set, and that is a
different kind of claim -- `requested`, not `reported`. Every value written
here is labelled with its source, and anything the launch configuration did
not fix is recorded as `couldnt_check` rather than filled in from a local
container that is not the machine the numbers came from.

This is a one-off. Future runs get the real thing from `describe()`.
"""
import json
import sys

PATH = "runs/arxiv-150k-via-characterize/verify_info.json"

# What corpora/run_verify_pod.sh passed to `postgres -c ...`, and what the
# session spec set. Values are strings exactly as given on the command line.
PGVECTOR_LAUNCH = {
    "shared_buffers": "256MB",
    "maintenance_work_mem": "512MB",
    "max_parallel_workers_per_gather": "0",
}
# Settings the launch configuration did NOT fix. The server defaults are
# knowable in principle, but this pod is gone and a default read off a
# different machine is not this machine's value.
PGVECTOR_UNKNOWN = ("work_mem", "max_connections", "effective_cache_size",
                    "random_page_cost", "synchronous_commit", "jit",
                    "max_parallel_maintenance_workers")

QDRANT_LAUNCH = {
    "indexing_threshold": 1,
    "note": "the rest of Qdrant's configuration is on the collection and is "
            "already recorded in engine_facts.index_params",
}


def backfill(doc):
    changed = []
    for b in doc.get("engines", []):
        name = b.get("engine")
        facts = b.setdefault("engine_facts", {}) or {}
        ep = b.get("engine_params") or {}
        rs = {
            "source": "launch configuration (corpora/run_verify_pod.sh and "
                      "the session spec), NOT read back from the engine",
            "backfilled_by": "tasks/scratch/015-backfill-runtime-settings.py",
            "why_not_read_back": (
                "the adapters read these from the engine from task 015 "
                "onward; this run predates that and pod z01d7n4buc1a6i is "
                "terminated, so nothing can be asked of it now"),
        }
        if name == "pgvector":
            rs.update(PGVECTOR_LAUNCH)
            for k in PGVECTOR_UNKNOWN:
                rs[k] = "couldnt_check: not fixed by the launch configuration"
            rs["hnsw.ef_search_applied"] = ep.get("hnsw_ef")
            rs["hnsw.ef_search_source"] = "verify_info.engine_params.hnsw_ef"
            rs["index_build"] = "synchronous"
            rs["index_build_note"] = (
                "CREATE INDEX does not return until the HNSW graph is built, "
                "so pgvector's index cost is INSIDE the ingest phase. Qdrant "
                "indexes in the background and reports it separately; the "
                "two engines' ingest rates are not the same quantity until "
                "this is added.")
            rs["tuning"] = (
                "ENGINE DEFAULTS apart from the three settings above. No "
                "COPY, no unlogged tables, no synchronous_commit=off, no "
                "shared_buffers sized to the corpus. A tuned pgvector row is "
                "future work and is not what this run measured.")
        elif name == "qdrant":
            rs.update(QDRANT_LAUNCH)
            rs["index_build"] = "background"
            rs["index_build_note"] = (
                "Qdrant builds its HNSW graph asynchronously, so the measured "
                "ingest rate excludes it; the wait is reported separately as "
                "index.seconds.")
            rs["tuning"] = (
                "ENGINE DEFAULTS apart from indexing_threshold, which is set "
                "to 1 so a graph is built at all (task 009). No gRPC, no "
                "quantization, no sharding.")
        else:
            continue
        facts["runtime_settings"] = rs
        b["engine_facts"] = facts
        changed.append(name)
    doc["runtime_settings_note"] = (
        "engine_facts.runtime_settings for this run was backfilled from the "
        "launch configuration, not read back from the engines -- see each "
        "engine's runtime_settings.source. Runs from task 015 onward read it "
        "from the engine at describe() time.")
    return changed


if __name__ == "__main__":
    with open(PATH, encoding="utf-8") as f:
        doc = json.load(f)
    changed = backfill(doc)
    with open(PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"backfilled runtime_settings for: {', '.join(changed)}")
    for b in doc["engines"]:
        rs = (b.get("engine_facts") or {}).get("runtime_settings") or {}
        print(f"\n  {b['engine']}:")
        for k in sorted(rs):
            if k in ("why_not_read_back", "index_build_note", "tuning",
                     "backfilled_by", "note"):
                continue
            print(f"    {k:34} {rs[k]}")
