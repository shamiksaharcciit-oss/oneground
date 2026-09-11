#!/usr/bin/env bash
# Reproduce the pod's apt state and measure the scoped update + install.
#
# The pod is Ubuntu 24.04 (noble) with /var/lib/apt/lists STRIPPED. That is
# the fact session 20260911-164815 established and the fact the previous fix
# got wrong: the 75 MB seen growing in session 20260911-104406 was apt
# building the indices from empty, not the image shipping them.
#
# The pod carries four sources: Ubuntu + security (deb822 ubuntu.sources), the
# deadsnakes PPA, and NVIDIA's CUDA repo. Scoping means refreshing only the
# first and PGDG.
set -u
export DEBIAN_FRONTEND=noninteractive

PG_MAJOR=16
PG_CODENAME=noble
PG_VERSION_PIN="16.15-1.pgdg24.04+2"
PGVECTOR_VERSION_PIN="0.8.6-1.pgdg24.04+1"

say() { echo; echo "=== $* ==="; }

say "1. HARNESS BOOTSTRAP -- the pod already has curl + ca-certificates"
# run_verify_pod.sh uses curl for the qdrant binary long before this point.
# ubuntu:24.04 has neither, and with lists stripped they cannot be installed
# without an update first. Excluded from every number below.
apt-get update -qq >/dev/null 2>&1
apt-get install -y -qq --no-install-recommends curl ca-certificates >/dev/null 2>&1
echo "  curl: $(command -v curl), ca-certificates installed (harness only)"

say "2. reproduce the pod: strip lists, add its other two sources"
rm -rf /var/lib/apt/lists; mkdir -p /var/lib/apt/lists/partial
echo "  lists after stripping: $(du -sb /var/lib/apt/lists | cut -f1) bytes"
cat > /etc/apt/sources.list.d/cuda.list <<'EOF'
deb https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64 /
EOF
cat > /etc/apt/sources.list.d/deadsnakes-ubuntu-ppa-noble.sources <<'EOF'
Types: deb
URIs: https://ppa.launchpadcontent.net/deadsnakes/ppa/ubuntu/
Suites: noble
Components: main
EOF
echo "  sources.list.d: $(ls /etc/apt/sources.list.d/ | tr '\n' ' ')"

say "3. the CUDA index, by HEAD only -- what scoping avoids downloading"
for f in Packages Packages.gz; do
  sz=$(curl -sIL --max-time 60 \
    "https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/$f" \
    | awk 'BEGIN{IGNORECASE=1}/^content-length:/{v=$2}END{gsub("\r","",v); print v}')
  [ -n "${sz:-}" ] && echo "  cuda $f: $sz bytes"
done

say "4. PGDG key and source, and the scoped source set"
install -d /usr/share/postgresql-common/pgdg
curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
  -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${PG_CODENAME}-pgdg main" \
  > /etc/apt/sources.list.d/pgdg.list
rm -rf /etc/apt/oneground.sources.d
mkdir -p /etc/apt/oneground.sources.d
cp /etc/apt/sources.list.d/ubuntu.sources /etc/apt/oneground.sources.d/ 2>/dev/null || true
cp /etc/apt/sources.list.d/pgdg.list      /etc/apt/oneground.sources.d/
echo "  scoped : $(ls /etc/apt/oneground.sources.d/ | tr '\n' ' ')"
echo "  excluded: cuda.list deadsnakes-ubuntu-ppa-noble.sources"

say "5. (a) SCOPED apt-get update -- Ubuntu + PGDG, from stripped lists"
rm -rf /var/lib/apt/lists; mkdir -p /var/lib/apt/lists/partial
t0=$(date +%s)
apt-get update \
  -o Dir::Etc::sourcelist=/dev/null \
  -o Dir::Etc::sourceparts=/etc/apt/oneground.sources.d \
  -o APT::Get::List-Cleanup=0 2>&1 | grep -E "^(Fetched|W:|E:)" | tail -5
t1=$(date +%s)
SCOPED_SECS=$(( t1 - t0 ))
SCOPED_BYTES=$(du -sb /var/lib/apt/lists | cut -f1)
echo "  scoped update: ${SCOPED_SECS}s, lists on disk ${SCOPED_BYTES} bytes"
echo "  sources actually refreshed:"
ls /var/lib/apt/lists/*_Packages* 2>/dev/null | sed 's|.*/||; s/^/    /' | head -12
echo "  cuda/deadsnakes indices present? \
$(ls /var/lib/apt/lists/ 2>/dev/null | grep -cE 'nvidia|launchpad') (want 0)"

say "6. the five dependencies session 20260911-164815 could not install"
for pkg in locales ssl-cert libllvm19 libxslt1.1 postgresql-common; do
  cand=$(apt-cache policy "$pkg" 2>/dev/null | awk '/Candidate:/{print $2}')
  echo "  $(printf '%-20s' "$pkg") candidate: ${cand:-<none>}"
done

say "7. (b) pinned install, DOWNLOAD ONLY -- the dependency payload"
t0=$(date +%s)
apt-get install -y -q --no-install-recommends --download-only \
  "postgresql-${PG_MAJOR}=${PG_VERSION_PIN}" \
  "postgresql-${PG_MAJOR}-pgvector=${PGVECTOR_VERSION_PIN}" 2>&1 \
  | grep -E "Need to get|Fetched|^E:" | sed 's/^/  /'
t1=$(date +%s)
DL_SECS=$(( t1 - t0 ))
DEB_BYTES=$(du -sb /var/cache/apt/archives 2>/dev/null | cut -f1)
DEB_COUNT=$(ls /var/cache/apt/archives/*.deb 2>/dev/null | wc -l)
echo "  download-only: ${DL_SECS}s, cache ${DEB_BYTES} bytes across ${DEB_COUNT} packages"

say "8. install, then the rest of the pgvector path"
apt-get install -y -q --no-install-recommends \
  "postgresql-${PG_MAJOR}=${PG_VERSION_PIN}" \
  "postgresql-${PG_MAJOR}-pgvector=${PGVECTOR_VERSION_PIN}" >/dev/null 2>&1 \
  || { echo "  INSTALL FAILED"; exit 1; }
PGBIN="/usr/lib/postgresql/${PG_MAJOR}/bin"
"$PGBIN/postgres" --version | sed 's/^/  /'

mkdir -p /workspace
PGDATA=/var/lib/postgresql/oneground-pgdata
rm -rf "$PGDATA"; mkdir -p "$PGDATA"
chown -R postgres:postgres "$PGDATA"; chmod 700 "$PGDATA"
su postgres -c "$PGBIN/initdb -D $PGDATA --data-checksums -A trust" \
  >/workspace/pg-initdb.log 2>&1 || { echo "  initdb FAILED"; tail -5 /workspace/pg-initdb.log; exit 1; }
echo "  initdb OK"
touch /workspace/postgres.log; chown postgres:postgres /workspace/postgres.log
su postgres -c "$PGBIN/pg_ctl -D $PGDATA -l /workspace/postgres.log -o '-p 55432 -c maintenance_work_mem=512MB -c shared_buffers=256MB -c max_parallel_workers_per_gather=0' -w start" \
  >/dev/null || { echo "  START FAILED"; tail -5 /workspace/postgres.log; exit 1; }
echo "  server started"
su postgres -c "$PGBIN/createuser -p 55432 -s oneground" 2>/dev/null
su postgres -c "$PGBIN/createdb -p 55432 -O oneground oneground" 2>/dev/null
su postgres -c "$PGBIN/psql -p 55432 -d oneground -c 'CREATE EXTENSION IF NOT EXISTS vector'" >/dev/null
echo -n "  "; su postgres -c "$PGBIN/psql -p 55432 -d oneground -tAc \"SELECT 'pgvector ' || extversion FROM pg_extension WHERE extname='vector'\""
su postgres -c "$PGBIN/psql -p 55432 -d oneground -c \"CREATE TABLE t (id bigint PRIMARY KEY, embedding vector(3)); INSERT INTO t VALUES (1,'[1,0,0]'),(2,'[0,1,0]'); CREATE INDEX t_hnsw ON t USING hnsw (embedding vector_ip_ops) WITH (m=32, ef_construction=200);\"" >/dev/null
echo "  hnsw index built"
echo -n "  "; su postgres -c "$PGBIN/psql -p 55432 -h 127.0.0.1 -U oneground -d oneground -tAc \"SELECT 'tcp ok, server ' || current_setting('server_version')\""

say "SUMMARY (sizes are the transferable measurement; times are this laptop's link)"
echo "  (a) scoped index download : ${SCOPED_BYTES} bytes in ${SCOPED_SECS}s"
echo "  (b) dependency .deb payload: ${DEB_BYTES} bytes across ${DEB_COUNT} packages in ${DL_SECS}s"
echo "      at the pod's measured 191 KB/s to archive.ubuntu.com:"
echo "        indices  ~$(( SCOPED_BYTES / 195584 )) min"
echo "        packages ~$(( DEB_BYTES / 195584 )) min"
