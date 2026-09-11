import io
import sys

P = "tasks/015-pgvector.report.md"
s = io.open(P, encoding="utf-8").read()

STATUS_OLD = ("**Status: steps 1–4, 6 and 7 complete. Step 5 (the pod run) "
              "is prepared and\nwaiting on the developer's confirmation — "
              "see Blocked on developer.**")
STATUS_NEW = (
    "**Status: all eight steps complete.** The matched-environment pod run\n"
    "measured both engines on session 20260911-181410 (pod "
    "`z01d7n4buc1a6i`), after\nfive sessions and six environment faults — "
    "see *Step 5, fifth attempt* below.")

WAS5_OLD = ("**5. Matched-environment pod run** — prepared, not run. "
            "Awaiting the\ndeveloper's `y`.")
WAS5_NEW = ("**5. Matched-environment pod run** — done. Both engines, "
            "sequentially, on\none pod, one sample, one `environment_id`; the "
            "report issues a comparative\nlatency and qps verdict between two "
            "verified rows.")

RESULTS = """### Step 5, fifth attempt: session 20260911-181410 (pod z01d7n4buc1a6i)

Ran clean. Both engines sequentially: 150,000 vectors, 2,000 queries, dim 768,
concurrency 32, 200 qps offered, 5 minutes each. Terminated after `DONE`;
0 pods; this session ~$0.20.

**RTT ratio — what latency is attributable to, before any number is read:**

| engine | RTT p95 | sequential query p95 | rtt/query | attributable? |
| --- | --- | --- | --- | --- |
| qdrant 1.19.1 | 6.20 ms | 6.88 ms | **90%** | **no** — refused as environment noise |
| pgvector 0.8.6 | 0.81 ms | 14.46 ms | **5.6%** | **yes** |

The asymmetry is a fact about the *paths*, not the engines: Qdrant is reached
over HTTP, pgvector over a local Postgres connection. Qdrant's sequential p95
is refused not because Qdrant is slow but because at 6.88 ms the round trip is
90% of it. Both engines' **under-load** rows clear the 20% bar, which is why
the comparison below is allowed to exist at all.

**Per engine:**

| | qdrant 1.19.1 | pgvector 0.8.6 |
| --- | --- | --- |
| **p95 under load** (c=32) | **42.82 ms** | **385.90 ms** |
| **sustained qps** | **200.00** of 200 offered; 60,001 queries; 0 errors | **112.63** of 200; 33,790 queries; 0 errors |
| **recall@10** | **0.99945** | **0.99840** |
| recall@100 | 0.99806 | 0.99168 |
| **ingest** | **2,751 vectors/s** (150,000 in 54.5 s, durable) | **1,222 vectors/s** |
| index build | 2.5 s, **background** (excluded from ingest) | 0.012 s, **synchronous** (inside ingest) |
| **calibration error** | **−0.00190** | **−0.00085** |

Both calibration lines are `verified` against the 0.05 tolerance and sit in
`calibration/history.jsonl` with `environment z01d7n4buc1a6i`, `efSearch=128`,
`dataset arxiv-150k`. They are the **first Layer-2 points that reach a
verdict**: task 011's arXiv line carried no tolerance, and the arxiv-smoke
lines were both +0.00000 on a corpus small enough for HNSW to be exact.

Two numbers that look comparable and are not:

- **Ingest.** pgvector's 1,222/s *includes* its synchronous `CREATE INDEX`;
  Qdrant's 2,751/s *excludes* background indexing, reported separately as
  2.5 s. A reader comparing them has to add Qdrant's index time first.
- **qps.** Qdrant "meets" by sustaining exactly what it was offered — a
  sustain check, not a ceiling, and the decision log says so itself. pgvector
  sustaining 112.63 of the same offered 200 on the same host *is* a real
  finding.

**The decision log's two-engine comparison**, which is what step 5 exists to
produce:

```
[engine_comparison] single_node_hnsw[M=32,efConstruction=200,efSearch=128]:
  on latency_p95, qdrant is the better of 2 engines measured in environment
  z01d7n4buc1a6i -- qdrant 42.82 against pgvector 385.90. Both were measured
  on the same sample, on the same host, sequentially, and both carry fails
  against the constraint. Both ran on engine defaults except where the
  receipt says otherwise -- qdrant: engine defaults apart from
  indexing_threshold, which is set to 1 so a graph is built at all (task
  009); pgvector: engine defaults apart from the three settings above -- so
  this compares two default deployments, not two tuned ones, and a tuned row
  for either engine would be a different measurement.

[engine_comparison] ... on qps, qdrant is the better of 2 engines ... --
  qdrant 200.00 against pgvector 112.63 ... both carry meets against the
  constraint. [same tuning sentence]
```

Per-engine verdicts now appear in the option table:
`latency_p95@qdrant=fails qps@qdrant=meets latency_p95@pgvector=fails
qps@pgvector=fails`. **Nothing is recommended**: Qdrant misses the 40 ms
budget at 42.82, narrowly and genuinely — and see the fragility note below
before reading that as settled. The seven sharded rows correctly read
`no_engine_comparison`: neither engine built those architectures, so there is
nothing to compare.

**That latency verdict is fragile, and `docs/VERIFY.md` now says so.** The
same configuration measured **38.22 ms** on pod `tf8sd2usxbblsm` (session
20260909-225058) and **42.82 ms** here — **12% apart**, same GPU type, same
datacenter, same engine version, same parameters. The 40 ms constraint falls
between them: the first run's verdict was `meets`, this one's is `fails`, and
the architecture did not change. A latency verdict within ~15% of its
threshold is a sample of one from a distribution nobody has characterised.
Repeated runs reported as a spread are **task 017 work**.

### Engine runtime settings are now declared facts

`EngineFacts` gained `runtime_settings`, both adapters populate it from the
engine, and `as_dict()` now emits it — **along with `raw`, which it had
been silently dropping since task 009**, making a field whose whole purpose is
"so a later reader can check a claim this dataclass did not anticipate"
decorative.

pgvector reads `pg_settings` for `shared_buffers`, `work_mem`,
`maintenance_work_mem`, `max_connections`, `max_parallel_workers_per_gather`,
`max_parallel_maintenance_workers`, `effective_cache_size`,
`random_page_cost`, `synchronous_commit`, `jit` and `server_version`; plus
`index_build: synchronous` with the note about ingest, and `hnsw.ef_search`
split in two:

    hnsw.ef_search_applied   128   what the searches were made at
    hnsw.ef_search_session    40   what the connection holds now

That split is not pedantry. `search()` RESETs the GUC in a `finally`, so
reading it back afterwards returns the server default — and a receipt
saying `ef_search 40` for a run made at 128 would be worse than one saying
nothing. Caught by reading the first live output rather than by reasoning
about it.

Qdrant reports `hnsw_config`, `optimizer_config` (including
`indexing_threshold`, the setting that decides whether a graph is built at
all), `wal_config`, `quantization_config` and the shard/replica factors, plus
`index_build: background`.

**This run's settings are backfilled, and labelled as backfilled.** The pod is
terminated, so nothing can be read back from it. What the launch configuration
fixed is recorded with `source: launch configuration ... NOT read back from
the engine`; everything it did not fix — `work_mem`, `max_connections`,
`effective_cache_size` and four others — is `couldnt_check: not fixed by
the launch configuration`, rather than filled in from a local container that
is a different machine. Script:
`tasks/scratch/015-backfill-runtime-settings.py`.

## Observed, not done"""

TUNED_OLD = "**Neither engine is tuned.**"
TUNED_NEW = """**A tuned pgvector row.** Everything above measures two *default*
deployments, and the decision log now says so in the comparison sentence
itself. pgvector has obvious levers oneground did not pull: `COPY` instead of
batched upsert, `shared_buffers` sized to the corpus rather than 256 MB,
`synchronous_commit=off`, unlogged tables, a larger `work_mem` on the search
path. Several of them plausibly move the 385.90 ms p95 a long way. Pulling
them for one engine and not the other would break "no favourite"; pulling them
for both is a different task with its own brief. **Recorded, not done** —
and 385.90 ms should be read as *pgvector-as-it-ships*, never as pgvector's
ceiling.

**Neither engine is tuned.**"""

IMAGE_OLD = ("**A pre-baked pod image is the durable fix, and it is now one "
             "failure away\nfrom being this task's problem rather than "
             "017's.** Four sessions have been\nspent")
IMAGE_NEW = "**A pre-baked pod image, for task 017.** Five sessions were spent"

for old, new, label in ((STATUS_OLD, STATUS_NEW, "status"),
                        (WAS5_OLD, WAS5_NEW, "step 5 summary"),
                        ("## Observed, not done", RESULTS, "results"),
                        (TUNED_OLD, TUNED_NEW, "tuned row"),
                        (IMAGE_OLD, IMAGE_NEW, "pre-baked image")):
    if old not in s:
        print("MISS: " + label)
        sys.exit(1)
    s = s.replace(old, new, 1)
    print("ok: " + label)

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("report written")
