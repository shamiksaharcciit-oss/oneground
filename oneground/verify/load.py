"""Closed-loop load generator: throughput at a requested concurrency.

Task 009 measured latency *shape* -- one client, sequential -- and refused to
call it throughput. This is the other measurement: N workers issuing queries
concurrently against a token-bucket rate limit, for a fixed duration, with a
warm-up excluded.

What it measures
----------------
    achieved_qps      completed queries / measured seconds
    p50/p95/p99       per-query latency **under load**, which is a different
                      quantity from the single-client shape and is labelled so
    error_rate        failed queries / attempted
    engine_cpu_pct    the engine container's CPU, sampled from `docker stats`
    duration          measured seconds, warm-up excluded

What it does not measure
------------------------
**Recall.** Deliberately. Recall is measured on a separate sequential pass so
that a dropped or slow query under load can never be counted as a recall miss;
mixing them would let a saturated server look like a bad index. The two passes
share nothing but the corpus.

**The engine's maximum throughput.** A closed-loop generator with N workers
measures what N clients get, not what the server could do with more. If
`achieved_qps` sits well under `target_qps` the bottleneck is reported, not
diagnosed -- it could be the engine, the client, or the box they share.

Fairness
--------
Every engine in a matched comparison gets the same corpus, the same query set,
the same concurrency, the same target and the same duration, run sequentially
on the same host. Sequentially matters: two engines under load on one box are
measuring each other.
"""

import statistics
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

DEFAULT_CONCURRENCY = 8
DEFAULT_TARGET_QPS = 0            # 0 means unthrottled
DEFAULT_DURATION_MINUTES = 1.0
DEFAULT_WARMUP_SECONDS = 10.0


class TokenBucket:
    """A shared rate limit across workers.

    Refills continuously at `rate` per second with a small burst allowance, so
    the offered load approaches the target smoothly rather than in a sawtooth
    that would show up in the p99 as the generator's own artifact.
    """

    def __init__(self, rate, burst=None):
        self.rate = float(rate)
        self.capacity = float(burst if burst is not None else max(1.0, rate))
        self._tokens = self.capacity
        self._last = time.perf_counter()
        self._lock = threading.Lock()

    def take(self, timeout=5.0):
        """Block until a token is available. False if the timeout expires."""
        if self.rate <= 0:
            return True                       # unthrottled
        deadline = time.perf_counter() + timeout
        while True:
            with self._lock:
                now = time.perf_counter()
                self._tokens = min(self.capacity,
                                   self._tokens + (now - self._last) * self.rate)
                self._last = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
                need = (1.0 - self._tokens) / self.rate
            if time.perf_counter() + need > deadline:
                return False
            time.sleep(min(need, 0.01))


@dataclass
class LoadResult:
    """What a load phase produced. Every field measured, none inferred."""

    concurrency: int
    target_qps: float
    duration_seconds: float
    warmup_seconds: float
    completed: int
    errors: int
    latencies_ms: List[float] = field(default_factory=list)
    engine_cpu_pct: Optional[float] = None
    engine_mem_bytes: Optional[int] = None
    cpu_samples: int = 0

    @property
    def achieved_qps(self):
        return (self.completed / self.duration_seconds
                if self.duration_seconds > 0 else 0.0)

    @property
    def error_rate(self):
        attempted = self.completed + self.errors
        return self.errors / attempted if attempted else 0.0

    def percentiles(self):
        if not self.latencies_ms:
            return {}
        a = np.asarray(self.latencies_ms, dtype=np.float64)
        return {"p50_ms": float(np.percentile(a, 50)),
                "p95_ms": float(np.percentile(a, 95)),
                "p99_ms": float(np.percentile(a, 99)),
                "mean_ms": float(a.mean()),
                "max_ms": float(a.max())}

    def as_dict(self):
        d = {
            "concurrency": self.concurrency,
            "target_qps": self.target_qps,
            "achieved_qps": round(self.achieved_qps, 2),
            "completed": self.completed,
            "errors": self.errors,
            "error_rate": round(self.error_rate, 6),
            "duration_seconds": round(self.duration_seconds, 2),
            "warmup_seconds_excluded": self.warmup_seconds,
            "latency_under_load": self.percentiles(),
            "engine_cpu_pct": self.engine_cpu_pct,
            "engine_mem_bytes": self.engine_mem_bytes,
            "cpu_samples": self.cpu_samples,
            "note": ("latency here is measured UNDER LOAD at the stated "
                     "concurrency and is a different quantity from the "
                     "single-client latency shape. Recall is not measured "
                     "here; it comes from a separate sequential pass so load "
                     "can never be counted as a recall miss."),
        }
        if self.target_qps and self.achieved_qps < self.target_qps * 0.9:
            d["shortfall"] = (
                f"achieved {self.achieved_qps:.1f} qps against a target of "
                f"{self.target_qps:.0f}. Something is the bottleneck -- the "
                "engine, the client, or the host they share. This generator "
                "reports the shortfall; it does not diagnose it.")
        return d


class DockerStats:
    """Samples one container's CPU and memory in the background.

    Uses `docker stats --no-stream` on a timer rather than the streaming form:
    the stream emits ANSI control sequences and a fixed cadence we would have
    to parse around, and the sample rate here does not need to be precise.

    Every failure is swallowed into "no samples". CPU is a nice-to-have; a
    missing `docker` must not cost the run its latency numbers.
    """

    def __init__(self, container, interval=2.0):
        self.container = container
        self.interval = interval
        self.cpu, self.mem = [], []
        self._stop = threading.Event()
        self._thread = None

    def _sample(self):
        while not self._stop.is_set():
            try:
                p = subprocess.run(
                    ["docker", "stats", "--no-stream", "--format",
                     "{{.CPUPerc}}|{{.MemUsage}}", self.container],
                    capture_output=True, text=True, timeout=10,
                    encoding="utf-8", errors="replace")
                line = (p.stdout or "").strip().splitlines()
                if line:
                    cpu, _, mem = line[0].partition("|")
                    self.cpu.append(float(cpu.strip().rstrip("%")))
                    self.mem.append(_parse_bytes(mem.split("/")[0].strip()))
            except Exception:                         # noqa: BLE001
                pass
            self._stop.wait(self.interval)

    def start(self):
        if not self.container:
            return self
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        return self

    def summary(self):
        return {
            "cpu_pct": (round(statistics.mean(self.cpu), 1) if self.cpu
                        else None),
            "cpu_max_pct": (round(max(self.cpu), 1) if self.cpu else None),
            "mem_bytes": (int(statistics.mean(self.mem)) if self.mem else None),
            "samples": len(self.cpu),
        }


def _parse_bytes(text):
    """'123.4MiB' -> bytes. Returns 0 on anything unexpected."""
    text = (text or "").strip()
    units = {"B": 1, "KIB": 1024, "MIB": 1024 ** 2, "GIB": 1024 ** 3,
             "KB": 1000, "MB": 1000 ** 2, "GB": 1000 ** 3}
    for suffix, mult in sorted(units.items(), key=lambda x: -len(x[0])):
        if text.upper().endswith(suffix):
            try:
                return int(float(text[:-len(suffix)]) * mult)
            except ValueError:
                return 0
    return 0


def run_load(engine, namespace, queries, k=10, concurrency=DEFAULT_CONCURRENCY,
             target_qps=DEFAULT_TARGET_QPS,
             duration_minutes=DEFAULT_DURATION_MINUTES,
             warmup_seconds=DEFAULT_WARMUP_SECONDS, params=None,
             container=None, log_fn=None):
    """Closed-loop load. Returns a LoadResult.

    Workers pick queries round-robin from the supplied set, so every worker
    sees the same distribution and no worker gets a systematically easier
    slice. Warm-up runs the same code path and its results are discarded --
    the first queries against a fresh index pay for page-ins that a steady
    state does not.
    """
    def say(msg):
        if log_fn:
            log_fn(msg)

    n_q = len(queries)
    if n_q == 0:
        raise ValueError("run_load: no queries")

    bucket = TokenBucket(target_qps) if target_qps else None
    stop = threading.Event()
    lock = threading.Lock()
    lat, counters = [], {"completed": 0, "errors": 0}
    measuring = threading.Event()
    cursor = {"i": 0}

    def next_query():
        with lock:
            i = cursor["i"]
            cursor["i"] = (i + 1) % n_q
        return queries[i:i + 1] if i + 1 <= n_q else queries[0:1]

    def worker():
        while not stop.is_set():
            if bucket and not bucket.take(timeout=1.0):
                continue
            q = next_query()
            t0 = time.perf_counter()
            try:
                engine.search(namespace, q, k, params)
                dt = (time.perf_counter() - t0) * 1000.0
                if measuring.is_set():
                    with lock:
                        lat.append(dt)
                        counters["completed"] += 1
            except Exception:                         # noqa: BLE001
                if measuring.is_set():
                    with lock:
                        counters["errors"] += 1

    stats = DockerStats(container).start() if container else None
    workers = [threading.Thread(target=worker, daemon=True)
               for _ in range(int(concurrency))]

    say(f"load: {concurrency} workers, target "
        f"{target_qps or 'unthrottled'} qps, warm-up {warmup_seconds:.0f} s, "
        f"measuring {duration_minutes * 60:.0f} s")
    for w in workers:
        w.start()

    time.sleep(max(0.0, warmup_seconds))              # warm-up, discarded
    with lock:
        lat.clear()
        counters["completed"] = counters["errors"] = 0
    measuring.set()
    t_start = time.perf_counter()
    time.sleep(max(0.1, duration_minutes * 60.0))
    measured = time.perf_counter() - t_start
    measuring.clear()
    stop.set()
    for w in workers:
        w.join(timeout=10)
    if stats:
        stats.stop()

    s = stats.summary() if stats else {}
    result = LoadResult(
        concurrency=int(concurrency), target_qps=float(target_qps),
        duration_seconds=measured, warmup_seconds=float(warmup_seconds),
        completed=counters["completed"], errors=counters["errors"],
        latencies_ms=list(lat), engine_cpu_pct=s.get("cpu_pct"),
        engine_mem_bytes=s.get("mem_bytes"), cpu_samples=s.get("samples", 0))
    p = result.percentiles()
    say(f"load: {result.achieved_qps:.1f} qps achieved, "
        f"p95 {p.get('p95_ms', 0):.1f} ms, "
        f"errors {result.error_rate:.4%}"
        + (f", engine cpu {s['cpu_pct']}%" if s.get("cpu_pct") else ""))
    return result
