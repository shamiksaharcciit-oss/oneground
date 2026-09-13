#!/usr/bin/env bash
#
# Matched-environment verify, run on a RunPod pod.
#
# The client and the engine live on this one host, so the round trip is a
# loopback rather than the Windows Docker NAT that made task 009's latency
# couldnt_check. Every row this produces carries environment_id = the pod id.
#
# WHY A NATIVE BINARY AND NOT THE COMPOSE FILE
# --------------------------------------------
# A RunPod pod is itself a container, and running Docker inside one needs
# --privileged. RunPod's create API has no way to ask for it: POST /pods
# accepts 33 fields and none of them is privileged, capAdd, securityOpt,
# devices, sysctls or hostNetwork (measured in task 011,
# tasks/scratch/011-privileged-probe.py). So docker-in-docker is not
# available and the engine runs from its official release binary instead.
#
# The version is the same one the local compose file pins, so a pod run and a
# laptop run measure the same engine:
#
#     compose: qdrant/qdrant:v1.19.1
#     here:    qdrant-x86_64-unknown-linux-gnu.tar.gz from v1.19.1
#
# Env in (set by the session spec):
#   ONEGROUND_CONCURRENCY   closed-loop workers
#   ONEGROUND_TARGET_QPS    token-bucket target, 0 = unthrottled
#   ONEGROUND_DURATION_MIN  measured minutes, warm-up excluded
#   ONEGROUND_ENGINES       comma-separated: qdrant, pgvector (task 015)
#   ONEGROUND_REQUIREMENTS  path to the requirements file in the repo

set -euo pipefail

# Package whatever the verifier left behind. Called whether verify succeeded
# or not: `verify` writes verify.json BEFORE it prints its summary, so a
# failure after the write still leaves a complete measurement on disk. Session
# 20260909-213526 measured everything, crashed formatting the summary, and
# `set -e` killed the script before this ran -- the measurement existed and
# died with the pod.
#
# Returns 0 if anything was packaged, 1 if there was nothing to package.
package_outputs() {
    local workdir="$1" tarball="$2"
    local found=()
    for name in verify.json verify_info.json; do
        if [ -f "$workdir/$name" ]; then
            found+=("$name")
        else
            echo "  missing: $name"
        fi
    done
    if [ ${#found[@]} -eq 0 ]; then
        echo "  nothing to package"
        return 1
    fi
    # Bare filenames, tarred from inside the workdir: the members are exactly
    # what should appear in the destination directory, so the client extracts
    # into the output's `local` and the files land in the workdir. Prefixing
    # them with the workdir's basename is what put session 20260909-220900's
    # result in a stray directory at the repo root.
    tar -czf "$tarball" -C "$workdir" "${found[@]}"
    echo "  packaged ${#found[@]} file(s), $(stat -c %s "$tarball") bytes"
    return 0
}

# Sourcing this file with ONEGROUND_RUNNER_LIB=1 defines the functions above
# and runs nothing else, so `package_outputs` is tested as it actually ships
# rather than as a copy pasted into a fixture.
if [ -n "${ONEGROUND_RUNNER_LIB:-}" ]; then
    return 0
fi

QDRANT_VERSION="${QDRANT_VERSION:-v1.19.1}"
QDRANT_URL="https://github.com/qdrant/qdrant/releases/download/${QDRANT_VERSION}/qdrant-x86_64-unknown-linux-gnu.tar.gz"
ENGINES="${ONEGROUND_ENGINES:-qdrant}"

# Postgres + pgvector, pinned to the same versions the local compose file
# runs, so a pod row and a laptop row measure the same engine.
#
# WHY apt AND NOT THE UBUNTU ARCHIVE. Ubuntu 24.04's own universe ships
# postgresql-16-pgvector 0.6.0. The compose file pins 0.8.6. Installing from
# the Ubuntu archive would have produced a pod row measured against a
# different pgvector than every local row, and nothing in the receipt would
# have said so -- the extension version is what `describe()` reports, and it
# would simply have read 0.6.0 in one place and 0.8.6 in another. Resolved
# against the PGDG index before the first pod ran (task 015):
#
#     apt.postgresql.org  noble-pgdg  postgresql-16          16.15-1.pgdg24.04+2
#     apt.postgresql.org  noble-pgdg  postgresql-16-pgvector 0.8.6-1.pgdg24.04+1
#     ubuntu noble        universe    postgresql-16-pgvector 0.6.0
#
# WHY apt AND NOT THE BINARY TARBALL. The EDB tarball ships no extensions, so
# pgvector would have to be compiled against it on the pod -- a build
# toolchain and a compile inside a billed session, to arrive at the same
# binaries apt installs in about a minute. No Docker either way: this is a
# package install into the pod's own filesystem, which is what the brief asks
# for.
PG_MAJOR="${PG_MAJOR:-16}"
PG_VERSION_PIN="${PG_VERSION_PIN:-16.15-1.pgdg24.04+2}"
PGVECTOR_VERSION_PIN="${PGVECTOR_VERSION_PIN:-0.8.6-1.pgdg24.04+1}"
PG_CODENAME="${PG_CODENAME:-noble}"
PG_PORT="${PG_PORT:-55432}"
PG_USER="${PG_USER:-oneground}"
PG_DB="${PG_DB:-oneground}"
REQ="${ONEGROUND_REQUIREMENTS:-requirements.arxiv-150k.yaml}"
OUT_TARBALL="${OUT_TARBALL:-/workspace/verify-out.tgz}"

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

if [ -f .venv/bin/activate ]; then
    # shellcheck disable=SC1091
    . .venv/bin/activate
else
    echo "ERROR: no virtualenv at $REPO/.venv" >&2
    exit 1
fi

echo "=============================================================="
echo "oneground matched-environment verify"
echo "  repo        : $REPO"
echo "  python      : $(python --version 2>&1)"
echo "  engines     : $ENGINES"
echo "  requirements: $REQ"
# If these read as defaults, the launch did not carry the session env -- which
# is exactly what happened in session 20260909-194107. Fail early and say so
# rather than measuring the wrong thing for five minutes.
if [ -z "${ONEGROUND_REQUIREMENTS:-}" ]; then
    echo "ERROR: ONEGROUND_REQUIREMENTS is unset, so this run would verify" >&2
    echo "       '$REQ' by default rather than the session's own file." >&2
    echo "       The launch did not carry the session environment." >&2
    exit 2
fi
echo "  concurrency : ${ONEGROUND_CONCURRENCY:-8}"
echo "  target qps  : ${ONEGROUND_TARGET_QPS:-0}"
echo "  duration min: ${ONEGROUND_DURATION_MIN:-5}"
echo "  started     : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "--------------------------------------------------------------"

# --------------------------------------------------------- corpus preflight
# A volume-first session reads its corpus from the network volume, which the
# client cannot see. Everything here happens before an engine is downloaded or
# started, because a corpus problem costs seconds now and four minutes of pod
# time later -- which is how sessions 20260909-195824 and 20260909-205151 were
# spent.
#
# Confirmed layout (build 3's log): the volume holds the release tarball, not
# a loose directory. So a missing corpus is extracted from it, and then both
# files are checked against the repo's manifest -- the "same bytes as the
# local characterization" question, answered rather than assumed.
echo
echo "corpus preflight"
python - "$REQ" <<'ONEGROUND_PREFLIGHT'
import hashlib
import os
import sys
import tarfile

sys.path.insert(0, ".")
from oneground import intake

req = intake.load(sys.argv[1])
TARBALL = os.environ.get("ONEGROUND_CORPUS_TARBALL") or ""
MANIFEST = os.environ.get("ONEGROUND_CORPUS_MANIFEST") or ""

wanted = []
for label, cfg in (("vectors", req.vectors), ("queries", req.queries)):
    p = req.resolve((cfg or {}).get("path"))
    if p:
        wanted.append((label, p))


def human(n):
    return f"{n:,}"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def listing():
    print("")
    print("What is actually on the volume:")
    for root in ("/workspace", "/workspace/arxiv-150k"):
        if not os.path.isdir(root):
            continue
        print("  %s" % root)
        for name in sorted(os.listdir(root))[:40]:
            full = os.path.join(root, name)
            if os.path.isdir(full):
                print("    dir  %s" % name)
            else:
                print("    file %s  %s bytes" % (name, human(
                    os.path.getsize(full))))


missing = [(label, p) for label, p in wanted if not os.path.exists(p)]

# -- extract what is missing, from the release tarball on the volume
if missing:
    print("  absent: %s" % ", ".join(p for _label, p in missing))
    if not TARBALL or not os.path.exists(TARBALL):
        print("")
        print("ERROR: the corpus this session verifies is not on this pod,")
        print("       and neither is the tarball it would come from.")
        for label, p in missing:
            print("    %-8s %s" % (label, p))
        if TARBALL:
            print("    tarball  %s  (absent)" % TARBALL)
        listing()
        sys.exit(3)

    print("  extracting from %s (%s bytes)"
          % (TARBALL, human(os.path.getsize(TARBALL))))
    by_base = {os.path.basename(p): p for _label, p in missing}
    got = set()
    with tarfile.open(TARBALL) as tf:
        for member in tf:
            if not member.isfile():
                continue
            base = os.path.basename(member.name)
            dest = by_base.get(base)
            if dest is None or base in got:
                continue
            # Only the files this run reads. sample.jsonl.zst is 50 MB of
            # source records that `verify` never opens.
            out_dir = os.path.dirname(dest) or "."
            os.makedirs(out_dir, exist_ok=True)
            member.name = base          # strip the member's prefix
            tf.extract(member, out_dir, filter="data")
            got.add(base)
            print("    %s -> %s  (%s bytes)"
                  % (base, dest, human(os.path.getsize(dest))))
    still = [p for base, p in by_base.items() if base not in got]
    if still:
        print("")
        print("ERROR: the tarball does not contain what this session needs.")
        for p in still:
            print("    %s" % p)
        with tarfile.open(TARBALL) as tf:
            print("  members:")
            for name in tf.getnames()[:40]:
                print("    %s" % name)
        sys.exit(3)

# -- everything is present; report it
for label, p in wanted:
    print("  %-8s %s  (%s bytes)" % (label, p, human(os.path.getsize(p))))

# -- and prove it is the same corpus the local characterization was built from
#
# Run every time, not only after an extraction: the volume outlives the pod,
# so this directory can hold a partial extraction left by a session that was
# terminated mid-way. That is the case most likely to occur and the one a
# check on freshly-written files alone would miss.
if not MANIFEST:
    print("  digests   couldnt-check: no manifest declared for this session")
elif not os.path.exists(MANIFEST):
    print("")
    print("ERROR: the declared manifest is not in the repo: %s" % MANIFEST)
    sys.exit(3)
else:
    expected = {}
    with open(MANIFEST, encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) == 2:
                expected[parts[1]] = parts[0]
    bad = []
    for label, p in wanted:
        base = os.path.basename(p)
        want = expected.get(base)
        if want is None:
            print("  %-8s couldnt-check: %s is not in %s"
                  % (label, base, MANIFEST))
            continue
        got_digest = sha256(p)
        if got_digest == want:
            print("  %-8s sha256 %s  matches %s"
                  % (label, got_digest[:16], os.path.basename(MANIFEST)))
        else:
            bad.append((label, p, want, got_digest))
    if bad:
        print("")
        print("ERROR: the corpus on this volume is not the corpus this")
        print("       session's ground truth was built from. Verifying an")
        print("       engine against the wrong vectors would produce a")
        print("       recall number that means nothing.")
        for label, p, want, got_digest in bad:
            print("    %s  %s" % (label, p))
            print("      expected %s" % want)
            print("      actual   %s" % got_digest)
        sys.exit(3)
ONEGROUND_PREFLIGHT
echo "--------------------------------------------------------------"

# ------------------------------------------------------------- engine setup
#
# Engines are started TOGETHER and measured SEQUENTIALLY. Starting both up
# front costs a little idle memory and buys a much simpler failure mode: if
# the second engine cannot be installed, the run fails before any measurement
# rather than half way through, with one engine's numbers already written and
# the other's missing.
#
# They still never serve queries at the same time -- `oneground verify` walks
# the engine list in order -- so neither number carries the other's load. See
# docs/VERIFY.md on what "matched" does and does not guarantee.

has_engine() { case ",$ENGINES," in *,"$1",*) return 0 ;; *) return 1 ;; esac; }

# Task 017: the pre-baked image carries Postgres, pgvector and Qdrant already,
# at the same pins this script would install. The marker is what says so, and
# it carries the versions so the run can record WHICH image it ran on as an
# engine fact -- read from the image rather than from apt at run time.
BAKED_MARKER=/opt/oneground-image/BAKED
if [ -f "$BAKED_MARKER" ]; then
    ONEGROUND_BAKED=1
    echo "--------------------------------------------------------------"
    echo "pre-baked image detected; skipping apt and the qdrant download"
    cat "$BAKED_MARKER"
    # shellcheck disable=SC1090
    . "$BAKED_MARKER"
    QDRANT_VERSION="${qdrant_version:-$QDRANT_VERSION}"
    PG_VERSION_PIN="${pg_version:-$PG_VERSION_PIN}"
    PGVECTOR_VERSION_PIN="${pgvector_version:-$PGVECTOR_VERSION_PIN}"
else
    ONEGROUND_BAKED=0
fi
export ONEGROUND_BAKED

if has_engine pgvector; then
if [ "$ONEGROUND_BAKED" = "1" ]; then
    # The image HAS postgres and pgvector. It does not have a running server:
    # the Dockerfile creates PGDATA with the right owner and stops there,
    # because a data directory initialised at build time would bake a cluster
    # into the image and every pod would share its identity.
    #
    # So exactly the install is skipped here and [5/5] below still runs. This
    # was wrong in task 017: the whole block was gated on the image, install
    # AND start together, so postgres was present and never started, and
    # sessions 20260912-171431 and -175800 both died on
    # "pgvector: connection refused" -- the second one after the engine-list
    # drift had been fixed, which is what made it look like the same bug twice.
    echo "--------------------------------------------------------------"
    echo "postgresql-$PG_MAJOR + pgvector from the baked image; skipping apt"
    PGBIN="/usr/lib/postgresql/$PG_MAJOR/bin"
    "$PGBIN/postgres" --version
else
    echo "--------------------------------------------------------------"
    echo "installing postgresql-$PG_MAJOR + pgvector from apt.postgresql.org"
    export DEBIAN_FRONTEND=noninteractive
    # Each step announces itself. The session watchdog terminates a pod whose
    # log has not grown for 15 minutes, and a quiet `apt-get install` is
    # exactly the kind of step that looks like a hang from outside. These
    # echoes are what keep a slow-but-working install from being killed --
    # and, if it does fail, what says which step it died on.
    # WHY A SCOPED `apt-get update`, AND WHY NOT NONE AT ALL.
    #
    # Two sessions established the shape of this, each by being wrong:
    #
    #   20260911-104406  a bare `apt-get update` refreshed all four sources
    #                    and had not finished after 20 minutes.
    #   20260911-164815  "refresh PGDG only" then failed the install --
    #                    locales, ssl-cert, libllvm19, libxslt1.1 and
    #                    postgresql-common were "not installable".
    #
    # The second failed because the INDICES ARE ABSENT, not stale. The pod
    # image strips /var/lib/apt/lists, as almost every Docker image does, so
    # the 75 MB seen growing in the first session was apt building them from
    # empty -- not the image shipping them. Confirmed on the pod: after the
    # PGDG-only refresh, /var/lib/apt/lists held 1.9 MB and five entries, all
    # of them PGDG.
    #
    # So Ubuntu's indices must be fetched. What can be skipped is the two
    # sources nothing here needs: NVIDIA's CUDA repo and the deadsnakes PPA.
    # Measured in an ubuntu:24.04 container with lists stripped, which is the
    # pod's state:
    #
    #   scoped index fetch (Ubuntu + PGDG)    33.9 MB
    #   dependency .debs, 28 packages         76.9 MB
    #   total                                110.8 MB
    #   cuda index alone, skipped              7.7 MB (1.8 MB gzipped)
    #
    # Scoping is done by pointing apt at a directory holding only the sources
    # to refresh, which is plainer than a pile of -o overrides and leaves the
    # real sources.list.d untouched for anything else on the pod.
    echo "  [1/5] PGDG signing key and source (codename pinned: $PG_CODENAME)"
    install -d /usr/share/postgresql-common/pgdg
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc         -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $PG_CODENAME-pgdg main"         > /etc/apt/sources.list.d/pgdg.list
    # The codename is hard-coded rather than read from `lsb_release`, which is
    # not installed on this image -- and it is not a free choice anyway: the
    # version pins below are `pgdg24.04` builds, so the codename is already
    # decided by them. Reading it would only add a way for the two to disagree.

    echo "  [2/5] scoped apt-get update: Ubuntu + PGDG (CUDA and deadsnakes skipped)"
    rm -rf /etc/apt/oneground.sources.d
    mkdir -p /etc/apt/oneground.sources.d
    for f in /etc/apt/sources.list.d/ubuntu.sources /etc/apt/sources.list; do
        [ -s "$f" ] && cp "$f" /etc/apt/oneground.sources.d/
    done
    cp /etc/apt/sources.list.d/pgdg.list /etc/apt/oneground.sources.d/
    echo "        refreshing: $(ls /etc/apt/oneground.sources.d/ | tr '
' ' ')"
    t0=$(date +%s)
    # NOT -qq. The `Get:` lines are what let the 15-minute stall watchdog tell
    # a slow fetch from a hung one; at the rate this link has shown, the
    # difference decides whether the session survives. ~110 MB over the two
    # steps: about 9 minutes at the 191 KB/s a single-stream curl measured on
    # the pod, far longer if apt's effective rate is the ~16 KB/s that the
    # same session's index growth suggested. The log will say which.
    apt-get update         -o Dir::Etc::sourcelist=/dev/null         -o Dir::Etc::sourceparts=/etc/apt/oneground.sources.d         -o APT::Get::List-Cleanup=0
    echo "        refreshed in $(( $(date +%s) - t0 ))s"

    echo "  [3/5] dependency availability, before attempting the install"
    # The five that were "not installable" last time. Printed BEFORE the
    # install so the log distinguishes "the index fetch did not give us what
    # we need" from "the install broke for some other reason" -- last session
    # those looked identical until the madison output was read carefully.
    missing=0
    for pkg in locales ssl-cert libllvm19 libxslt1.1 postgresql-common; do
        cand=$(apt-cache policy "$pkg" 2>/dev/null                | awk '/Candidate:/{print $2}')
        case "${cand:-none}" in
            none|"(none)") echo "        $pkg: NOT AVAILABLE" >&2; missing=1 ;;
            *) echo "        $pkg: $cand" ;;
        esac
    done
    if [ "$missing" = 1 ]; then
        echo "ERROR: Ubuntu dependencies are unavailable after the scoped" >&2
        echo "  update, so the install cannot succeed. The indices are" >&2
        echo "  ABSENT rather than stale -- this image strips" >&2
        echo "  /var/lib/apt/lists -- so this means the scoped update did" >&2
        echo "  not actually fetch Ubuntu's. What it refreshed:" >&2
        ls /var/lib/apt/lists/ 2>/dev/null | grep -v partial | sed 's/^/    /' >&2
        exit 1
    fi

    # Pinned exactly. An unpinned install would drift the moment PGDG
    # publishes a point release, and the pod row would stop being comparable
    # to the local one without anything saying so.
    echo "  [4/5] postgresql-$PG_MAJOR=$PG_VERSION_PIN"
    echo "        postgresql-$PG_MAJOR-pgvector=$PGVECTOR_VERSION_PIN"
    echo "        (~77 MB of .debs across 28 packages)"
    t0=$(date +%s)
    if ! apt-get install -y -q --no-install-recommends         "postgresql-$PG_MAJOR=$PG_VERSION_PIN"         "postgresql-$PG_MAJOR-pgvector=$PGVECTOR_VERSION_PIN"; then
        echo "ERROR: the pinned PGDG packages could not be installed." >&2
        echo "  available postgresql-$PG_MAJOR-pgvector versions:" >&2
        apt-cache madison "postgresql-$PG_MAJOR-pgvector" >&2 || true
        echo "  available postgresql-$PG_MAJOR versions:" >&2
        apt-cache madison "postgresql-$PG_MAJOR" >&2 || true
        echo "  The five Ubuntu dependencies were checked above and were" >&2
        echo "  available, so this is NOT the absent-index failure of" >&2
        echo "  session 20260911-164815. Read the apt output above." >&2
        exit 1
    fi
    echo "        installed in $(( $(date +%s) - t0 ))s"

    echo "        versions"
    PGBIN="/usr/lib/postgresql/$PG_MAJOR/bin"
    "$PGBIN/postgres" --version
fi
    # ---- from here on, baked or not: the server has to be started either way

    echo "  [5/5] initdb + start"

    # Storage on the container disk, not the network volume, for the same
    # reason Qdrant's is: an engine's storage on a network mount measures the
    # mount. Task 006 measured a 30-minute venv install for that reason.
    #
    # NOT /root/pgdata. `/root` is drwx------ root root, so the postgres user
    # cannot TRAVERSE it however the data directory itself is owned --
    # chowning the directory looks like it should work and does not:
    #
    #     pg_ctl: could not access directory "/root/pgdata": Permission denied
    #
    # /var/lib/postgresql is created by postgresql-common, owned by postgres,
    # and on the container disk, which is what the paragraph above actually
    # asks for. Caught in a container before a third pod session paid for it.
    PGDATA=/var/lib/postgresql/oneground-pgdata
    rm -rf "$PGDATA"
    mkdir -p "$PGDATA"
    chown -R postgres:postgres "$PGDATA"
    chmod 700 "$PGDATA"
    # initdb and pg_ctl are checked explicitly. Chained with `&&` they failed
    # silently and the run carried on to three connection errors against a
    # server that had never started -- four messages for one fault, none of
    # them naming it.
    if ! su postgres -c "$PGBIN/initdb -D $PGDATA --data-checksums -A trust"         >/workspace/pg-initdb.log 2>&1; then
        echo "ERROR: initdb failed; last 20 lines:" >&2
        tail -20 /workspace/pg-initdb.log >&2
        exit 1
    fi
    # maintenance_work_mem matters: pgvector spills the HNSW build to disk
    # when it is too small, which makes index build time depend on a setting
    # nobody recorded. Same value as the local compose file.
    # pg_ctl's -l file is created by the POSTGRES process, not by this
    # shell, and /workspace is root-owned -- so postgres cannot create it:
    #
    #   /bin/sh: 1: cannot create /workspace/postgres.log: Permission denied
    #
    # Note the asymmetry that hides this. The `>/workspace/pg-initdb.log`
    # above is a redirect performed by the ROOT shell outside `su`, so
    # initdb's log lands fine and only the server's does not -- one of the
    # two logs working is what makes the other look like a postgres fault.
    # Pre-create it with the right owner, so the log still ends up where
    # the session collects its outputs.
    # /workspace is a NETWORK VOLUME and does not permit chown:
    #
    #   chown: changing ownership of '/workspace/postgres.log':
    #          Operation not permitted
    #
    # which killed session 20260911-174648 under `set -e`, 23 seconds
    # after the install finally succeeded. Pre-creating the file and
    # giving it to postgres was the previous fix for the previous fault
    # (postgres cannot create a file in root-owned /workspace) and it
    # traded one unwritable path for one unchownable one.
    #
    # So do not fight the volume at all. The server writes its log to a
    # directory postgres already owns, and the log is COPIED to
    # /workspace afterwards by root, which can read it and write there.
    # The copy is best-effort: a missing server log must never be the
    # thing that fails a run whose measurements are already taken.
    PG_LOG=/var/lib/postgresql/oneground-postgres.log
    : > "$PG_LOG"
    chown postgres:postgres "$PG_LOG"   # its own directory, not the volume
    if ! su postgres -c "$PGBIN/pg_ctl -D $PGDATA -l $PG_LOG -o '-p $PG_PORT -c maintenance_work_mem=512MB -c shared_buffers=256MB -c max_parallel_workers_per_gather=0' -w start"; then
        echo "ERROR: postgres did not start; last 20 lines of its log:" >&2
        tail -20 "$PG_LOG" >&2
        exit 1
    fi
    su postgres -c "$PGBIN/createuser -p $PG_PORT -s $PG_USER" || true
    su postgres -c "$PGBIN/createdb -p $PG_PORT -O $PG_USER $PG_DB" || true
    su postgres -c "$PGBIN/psql -p $PG_PORT -d $PG_DB -c         'CREATE EXTENSION IF NOT EXISTS vector'"
    echo "        extension"
    su postgres -c "$PGBIN/psql -p $PG_PORT -d $PG_DB -tAc         \"SELECT 'pgvector ' || extversion FROM pg_extension WHERE extname='vector'\""
fi

if has_engine qdrant; then
# The baked image already has the binary, at the pinned version, on the
# container disk rather than the network volume.
if [ "$ONEGROUND_BAKED" = "1" ] && [ -x "${qdrant_dir:-/opt/qdrant}/qdrant" ]; then
    ENGINE_DIR="${qdrant_dir:-/opt/qdrant}"
    echo "qdrant from the baked image: $ENGINE_DIR"
else
ENGINE_DIR=/workspace/engines/qdrant
mkdir -p "$ENGINE_DIR"
if [ ! -x "$ENGINE_DIR/qdrant" ]; then
    echo "fetching qdrant $QDRANT_VERSION (release binary, no docker needed)"
    curl -fsSL "$QDRANT_URL" -o /tmp/qdrant.tgz
    # --no-same-owner: the archive records uid/gid 1001, and root extracting
    # it tries to honour that and fails on a container filesystem. Under
    # `set -e` that killed the whole run before qdrant existed
    # (session 20260909-194107).
    tar -xzf /tmp/qdrant.tgz --no-same-owner --no-same-permissions \
        -C "$ENGINE_DIR"
    chmod +x "$ENGINE_DIR/qdrant"
fi
fi
"$ENGINE_DIR/qdrant" --version || true

# Storage on the container disk, not the network volume: an engine's storage
# on a network mount measures the mount. Task 006 measured a 30-minute venv
# install for the same reason.
export QDRANT__STORAGE__STORAGE_PATH=/root/qdrant-storage
export QDRANT__STORAGE__SNAPSHOTS_PATH=/root/qdrant-snapshots
export QDRANT__SERVICE__HTTP_PORT=6333
# Task 017g. The HTTP port was set from the start and the gRPC one never was,
# so whether gRPC listened on a pod depended on the release binary's bundled
# default -- and the adapter asked for HTTP anyway until 017f. Both now stated.
#
# This is not cosmetic. Session 20260913-161921 could not attribute Qdrant's
# latency at all: a 4.62 ms HTTP round trip was 60% of a 7.72 ms p95, over the
# 20% limit. gRPC is the cheaper transport, and whether it is listening
# decides whether that row reads "unanswerable" or becomes a number.
export QDRANT__SERVICE__GRPC_PORT=6334
export QDRANT__LOG_LEVEL=WARN
rm -rf "$QDRANT__STORAGE__STORAGE_PATH"
mkdir -p "$QDRANT__STORAGE__STORAGE_PATH"

echo "starting qdrant ..."
cd "$ENGINE_DIR"
setsid nohup ./qdrant > /workspace/qdrant.log 2>&1 < /dev/null &
cd "$REPO"

for i in $(seq 1 60); do
    if curl -fsS http://localhost:6333/ >/dev/null 2>&1; then
        echo "  qdrant up after ${i}s: $(curl -fsS http://localhost:6333/ | head -c 200)"
        break
    fi
    sleep 1
done
curl -fsS http://localhost:6333/ >/dev/null 2>&1 || {
    echo "ERROR: qdrant did not start; last 40 lines of its log:" >&2
    tail -40 /workspace/qdrant.log >&2
    exit 1
}
else
    echo "qdrant not in ENGINES ($ENGINES); skipping its setup"
fi

# ------------------------------------------------------------------- verify
# The RTT baseline is measured first, inside `oneground verify`, and lands at
# the top of verify.json -- so a reader sees what the path cost before seeing
# any latency attributed to the engine.
export ONEGROUND_ENVIRONMENT_ID="${RUNPOD_POD_ID:-${ONEGROUND_SESSION:-unknown-pod}}"
echo
echo "environment_id: $ONEGROUND_ENVIRONMENT_ID"
echo "running oneground verify (target: existing endpoint on this host) ..."
# The exit code is captured rather than left to `set -e`, so that the outputs
# get packaged either way. See package_outputs at the top of this file.
VERIFY_RC=0
python -m oneground.cli verify "$REQ" --on-pod || VERIFY_RC=$?

# ---------------------------------------------------------------- outputs
WORKDIR="$(python -c "
import sys, os
sys.path.insert(0, '.')
from oneground import intake
r = intake.load(sys.argv[1])
print(r.resolve(r.workdir))
" "$REQ")"

echo
echo "packaging outputs from $WORKDIR"
PACKAGE_RC=0
package_outputs "$WORKDIR" "$OUT_TARBALL" || PACKAGE_RC=$?


# The postgres server log, carried to the volume for the receipt.
#
# It is written to a directory postgres owns rather than straight to
# /workspace, because /workspace is a network volume: root can write there but
# NOTHING can chown there, and postgres cannot create a file there itself.
# Session 20260911-174648 died on that chown, 23 seconds after the install
# finally succeeded -- the previous fix for the previous fault had traded an
# unwritable path for an unchownable one.
#
# So the copy happens here instead, as root, after the measurements are
# packaged. `|| true` on every line and no `set -e` exposure: a server log
# that cannot be copied must never be the thing that fails a run whose
# numbers are already taken and already in the tarball.
if [ -n "${PG_LOG:-}" ] && [ -f "$PG_LOG" ]; then
    if cp "$PG_LOG" /workspace/postgres.log 2>/dev/null; then
        echo "  copied postgres server log -> /workspace/postgres.log"
    else
        echo "  could not copy $PG_LOG to /workspace (not fatal); it stays at"
        echo "    $PG_LOG on the pod's own disk"
    fi
fi

echo "  finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo

# DONE is the marker `watch` fetches and terminates on, and it means the run
# succeeded -- not merely that it stopped. A failed verify must never print
# it, however much of the measurement survived.
if [ "$VERIFY_RC" -ne 0 ]; then
    echo "VERIFY FAILED: oneground verify exited $VERIFY_RC."
    if [ "$PACKAGE_RC" -eq 0 ]; then
        echo "Whatever it had written is in $OUT_TARBALL and the traceback is"
        echo "above. This run produced no verdict."
    fi
    exit "$VERIFY_RC"
fi
if [ "$PACKAGE_RC" -ne 0 ]; then
    echo "VERIFY SUCCEEDED BUT PRODUCED NO OUTPUTS -- nothing to bring back."
    exit 1
fi

echo "DONE"
echo "$OUT_TARBALL"
