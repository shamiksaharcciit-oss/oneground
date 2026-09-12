# The pre-baked oneground pod image. Task 017 item 1.
#
# WHY THIS EXISTS
# ---------------
# Six environment faults across five billed sessions in task 015, none of them
# a measurement and every one of them paid for at pod rates:
#
#   20260911-001111  git clone checked out a branch that no longer existed
#   20260911-104406  a bare `apt-get update` refreshed four sources and stalled
#   20260911-164815  "PGDG only" then failed the install on unmet dependencies
#   20260911-174648  PGDATA under /root, which postgres cannot traverse
#   20260911-181410  /workspace not writable by postgres, then not chownable
#                    (two faults, fixed in two passes)
#
# Every one of them was setup, not work. The durable fix is to do the setup
# once, here, where a failure costs a CI minute instead of a pod session, and
# where the result is a digest that either exists or does not.
#
# WHAT IS NOT IN HERE
# -------------------
# The repo. The bundle still syncs at session time, because the whole point of
# a session is to run the commit under test -- an image with the repo baked in
# would measure whatever was current when the image was built.
#
# PINS
# ----
# Everything is pinned and every pin matches what the local compose files run,
# so a pod row and a laptop row measure the same engines. Changing any of them
# is changing what gets measured; the workflow rebuilds and re-locks the digest.

FROM runpod/pytorch:1.1.0-cu1300-torch291-ubuntu2404

# Matching corpora/run_verify_pod.sh exactly. Resolved against the PGDG index
# in task 015; Ubuntu noble's own universe ships pgvector 0.6.0, and the
# compose file pins 0.8.6, so the archive is not an option -- a pod row would
# have measured a different extension than every local row with nothing in the
# receipt saying so.
ARG QDRANT_VERSION=v1.19.1
ARG PG_MAJOR=16
ARG PG_CODENAME=noble
ARG PG_VERSION_PIN=16.15-1.pgdg24.04+2
ARG PGVECTOR_VERSION_PIN=0.8.6-1.pgdg24.04+1
ARG RUNPODCTL_VERSION=v1.14.4

ENV DEBIAN_FRONTEND=noninteractive \
    ONEGROUND_POD_IMAGE=1 \
    ONEGROUND_VENV=/opt/oneground-venv \
    ONEGROUND_QDRANT_DIR=/opt/qdrant \
    PGDATA=/var/lib/postgresql/oneground-pgdata \
    PG_LOG=/var/lib/postgresql/oneground-postgres.log

# ---------------------------------------------------------------- base tools
# A scoped source list from the start. The stall in 20260911-104406 was four
# sources being refreshed (CUDA and deadsnakes among them), not a slow link:
# the scoped fetch measured 33.9 MB and the pinned install 76.9 MB, together
# about 110 MB and under a minute. Baking it means the pod pays neither.
RUN set -eux; \
    apt-get update -q; \
    apt-get install -y -q --no-install-recommends \
        ca-certificates curl gnupg git tar; \
    rm -rf /var/lib/apt/lists/*

# ------------------------------------------------- postgres 16 + pgvector
# The signing key and a source file of its own, so the update below can be
# scoped to exactly Ubuntu + PGDG the way the run-time script learned to do it.
RUN set -eux; \
    install -d -m 0755 /usr/share/postgresql-common/pgdg; \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc; \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
https://apt.postgresql.org/pub/repos/apt ${PG_CODENAME}-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update -q; \
    apt-get install -y -q --no-install-recommends \
        "postgresql-${PG_MAJOR}=${PG_VERSION_PIN}" \
        "postgresql-${PG_MAJOR}-pgvector=${PGVECTOR_VERSION_PIN}"; \
    rm -rf /var/lib/apt/lists/*

# The directories, pre-created and owned, which is the whole of faults 4 and 5.
#
# PGDATA is NOT under /root: /root is drwx------, so the postgres user cannot
# traverse it, and chowning the leaf does not help because the parent is still
# unreadable. The log is NOT under /workspace: that is the network volume, it
# is not writable by postgres, and it is not chownable either -- three
# distinct properties that produced three separate failures. Both live
# somewhere postgres already owns.
RUN set -eux; \
    install -d -o postgres -g postgres -m 0700 "$PGDATA"; \
    install -d -o postgres -g postgres -m 0755 /var/lib/postgresql; \
    touch "$PG_LOG"; \
    chown postgres:postgres "$PG_LOG"; \
    chmod 0644 "$PG_LOG"

# ---------------------------------------------------------------- qdrant
# The release binary, not a container: RunPod cannot grant the privileges
# docker-in-docker wants (measured, task 011).
RUN set -eux; \
    mkdir -p "$ONEGROUND_QDRANT_DIR"; \
    curl -fsSL "https://github.com/qdrant/qdrant/releases/download/${QDRANT_VERSION}/qdrant-x86_64-unknown-linux-gnu.tar.gz" \
        -o /tmp/qdrant.tgz; \
    tar -xzf /tmp/qdrant.tgz -C "$ONEGROUND_QDRANT_DIR"; \
    rm -f /tmp/qdrant.tgz; \
    "$ONEGROUND_QDRANT_DIR/qdrant" --version

# ---------------------------------------------------------------- runpodctl
RUN set -eux; \
    curl -fsSL "https://github.com/runpod/runpodctl/releases/download/${RUNPODCTL_VERSION}/runpodctl-linux-amd64" \
        -o /usr/local/bin/runpodctl; \
    chmod +x /usr/local/bin/runpodctl; \
    runpodctl version || true

# ---------------------------------------------------------------- the venv
# Isolated at /opt/oneground-venv, built with --copies for the same reason the
# run-time script does: a symlinked venv on a network mount is where most of
# the 30-minute install in task 006 went. Only requirements.txt is copied in --
# the repo is not in this image, and a change to requirements.txt is what
# rebuilds it.
COPY requirements.txt /tmp/requirements.txt
RUN set -eux; \
    python3.12 -m venv --copies "$ONEGROUND_VENV"; \
    "$ONEGROUND_VENV/bin/python" -m pip install --upgrade pip; \
    "$ONEGROUND_VENV/bin/pip" install --no-cache-dir -r /tmp/requirements.txt; \
    "$ONEGROUND_VENV/bin/python" -c "import numpy, faiss, torch; \
print('numpy', numpy.__version__, 'faiss', faiss.__version__, 'torch', torch.__version__)"; \
    rm -f /tmp/requirements.txt

# ---------------------------------------------------------------- the marker
# What the scripts look for to skip apt and pip. It carries the versions rather
# than just existing, so a session that finds it can record WHICH image it ran
# on as an engine fact -- read from the image, not from apt at run time.
RUN set -eux; \
    install -d /opt/oneground-image; \
    { \
      echo "oneground_pod_image=1"; \
      echo "qdrant_version=${QDRANT_VERSION}"; \
      echo "pg_major=${PG_MAJOR}"; \
      echo "pg_version=${PG_VERSION_PIN}"; \
      echo "pgvector_version=${PGVECTOR_VERSION_PIN}"; \
      echo "venv=${ONEGROUND_VENV}"; \
      echo "qdrant_dir=${ONEGROUND_QDRANT_DIR}"; \
      echo "pgdata=${PGDATA}"; \
      echo "pg_log=${PG_LOG}"; \
    } > /opt/oneground-image/BAKED; \
    cat /opt/oneground-image/BAKED

# A build that cannot answer these is not a usable image, and finding that out
# in CI is the entire point of building it here.
RUN set -eux; \
    test -x "$ONEGROUND_QDRANT_DIR/qdrant"; \
    test -x "$ONEGROUND_VENV/bin/python"; \
    test -d "$PGDATA"; \
    "/usr/lib/postgresql/${PG_MAJOR}/bin/postgres" --version; \
    su postgres -c "/usr/lib/postgresql/${PG_MAJOR}/bin/initdb --version"; \
    ls /usr/share/postgresql/${PG_MAJOR}/extension/vector*.control

WORKDIR /root
