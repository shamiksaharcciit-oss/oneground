#!/usr/bin/env bash
# Restart one engine between load runs. Task 017b.
#
# WHY THIS EXISTS
# ---------------
# `verify.runs: N` (task 017 item 2) repeats the load phase so the report can
# state a run-to-run spread instead of implying there is none. That is only a
# second SAMPLE if the engine is restarted between runs -- otherwise run 2 is
# measuring a process with run 1's page cache warm and its allocator settled,
# which is a continuation of run 1 rather than an independent draw.
#
# On a laptop `restart_engine()` uses `docker restart`, because the engines are
# containers. On a pod they are native processes: qdrant is a release binary
# started with setsid/nohup, postgres is started by pg_ctl. There was no
# mechanism to restart either, so `restart_engine()` reported
# "not restarted: no engine_restart_command and no known container" -- honest,
# recorded per run, and it would have meant the first pod spread was measured
# across runs that quietly shared a warm process. This is that mechanism.
#
# The stop and start paths deliberately mirror corpora/run_verify_pod.sh
# exactly: same PGDATA, same log destinations, same postgres flags, same
# qdrant storage paths and environment. An engine restarted onto different
# settings than it was started with would make the spread a measurement of the
# difference between the two, which is worse than no restart at all.
#
#     bash corpora/restart_engine.sh qdrant
#     bash corpora/restart_engine.sh pgvector
#
# Exits non-zero if the engine does not come back. `restart_engine()` reads
# that and records it; a failed restart must not be reported as a successful
# one.

set -euo pipefail

ENGINE="${1:-}"
if [ -z "$ENGINE" ]; then
    echo "usage: restart_engine.sh <qdrant|pgvector>" >&2
    exit 2
fi

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# The same defaults run_verify_pod.sh uses, and the same env overrides, so the
# two cannot drift apart silently.
PG_MAJOR="${PG_MAJOR:-16}"
PG_PORT="${PG_PORT:-55432}"
PGDATA="${PGDATA:-/var/lib/postgresql/oneground-pgdata}"
PG_LOG="${PG_LOG:-/var/lib/postgresql/oneground-postgres.log}"
PGBIN="/usr/lib/postgresql/$PG_MAJOR/bin"

QDRANT_HTTP="${QDRANT_HTTP:-http://localhost:6333}"
QDRANT_LOG="${QDRANT_LOG:-/workspace/qdrant.log}"

case "$ENGINE" in
qdrant)
    ENGINE_DIR="${ONEGROUND_QDRANT_DIR:-}"
    if [ -z "$ENGINE_DIR" ]; then
        if [ -x /opt/qdrant/qdrant ]; then
            ENGINE_DIR=/opt/qdrant                    # the baked image
        else
            ENGINE_DIR=/workspace/engines/qdrant
        fi
    fi

    echo "restart: stopping qdrant"
    pkill -x qdrant 2>/dev/null || true
    for _ in $(seq 1 30); do
        pgrep -x qdrant >/dev/null 2>&1 || break
        sleep 1
    done
    # SIGKILL only if it ignored the polite request. A qdrant that will not
    # exit is a finding, not something to paper over, so it is said out loud.
    if pgrep -x qdrant >/dev/null 2>&1; then
        echo "restart: qdrant did not exit in 30 s; sending SIGKILL" >&2
        pkill -9 -x qdrant 2>/dev/null || true
        sleep 2
    fi

    # Storage is NOT cleared: the point is to restart the process, not to
    # rebuild the index. A run against a freshly ingested collection would be
    # measuring ingest, and the corpus is the same corpus across runs.
    export QDRANT__STORAGE__STORAGE_PATH="${QDRANT__STORAGE__STORAGE_PATH:-/root/qdrant-storage}"
    export QDRANT__STORAGE__SNAPSHOTS_PATH="${QDRANT__STORAGE__SNAPSHOTS_PATH:-/root/qdrant-snapshots}"
    export QDRANT__SERVICE__HTTP_PORT="${QDRANT__SERVICE__HTTP_PORT:-6333}"
    export QDRANT__LOG_LEVEL="${QDRANT__LOG_LEVEL:-WARN}"

    echo "restart: starting qdrant from $ENGINE_DIR"
    cd "$ENGINE_DIR"
    setsid nohup ./qdrant >> "$QDRANT_LOG" 2>&1 < /dev/null &
    cd "$REPO"

    for i in $(seq 1 60); do
        if curl -fsS "$QDRANT_HTTP/" >/dev/null 2>&1; then
            echo "restart: qdrant up after ${i}s"
            exit 0
        fi
        sleep 1
    done
    echo "ERROR: qdrant did not come back within 60 s; last 40 lines:" >&2
    tail -40 "$QDRANT_LOG" >&2 || true
    exit 1
    ;;

pgvector)
    echo "restart: stopping postgres"
    # -m fast: roll back open transactions and exit, rather than waiting for
    # clients to disconnect. The load generator's connections are exactly the
    # clients that would never disconnect on their own.
    su postgres -c "$PGBIN/pg_ctl -D $PGDATA -m fast -w stop" || true

    echo "restart: starting postgres"
    # The flags are the ones run_verify_pod.sh starts it with. Restarting onto
    # different settings would make the spread a measurement of the settings.
    if ! su postgres -c "$PGBIN/pg_ctl -D $PGDATA -l $PG_LOG \
-o '-p $PG_PORT -c maintenance_work_mem=512MB -c shared_buffers=256MB -c max_parallel_workers_per_gather=0' \
-w start"; then
        echo "ERROR: postgres did not come back; last 40 lines of $PG_LOG:" >&2
        tail -40 "$PG_LOG" >&2 || true
        exit 1
    fi

    for i in $(seq 1 60); do
        if su postgres -c "$PGBIN/pg_isready -p $PG_PORT" >/dev/null 2>&1; then
            echo "restart: postgres accepting connections after ${i}s"
            exit 0
        fi
        sleep 1
    done
    echo "ERROR: postgres started but never accepted connections" >&2
    exit 1
    ;;

*)
    echo "restart_engine.sh: unknown engine '$ENGINE'" >&2
    exit 2
    ;;
esac
