# The pre-baked pod image

A pod session runs a pre-baked image that already has Postgres 16, pgvector,
Qdrant, `runpodctl` and the pinned venv in it. Sessions reference it **by
digest**, never by tag, and `docker/pod/IMAGE.lock` is what says which digest.

## Why it exists

Six environment faults across five billed sessions in task 015, none of them a
measurement and every one paid for at pod rates: a clone of a branch that no
longer existed, a bare `apt-get update` that stalled on four sources, an
install that failed on unmet dependencies, `PGDATA` under `/root` which
postgres cannot traverse, and `/workspace` neither writable nor chownable by
postgres. Every one was setup, not work. Doing the setup once, in a Dockerfile,
moves those failures to a place where they cost a CI minute instead of a
session.

## Why a digest and never a tag

A tag is a name that can be moved. Two sessions a week apart naming the same
tag can run different bytes, and nothing in either receipt would say so. That
is the same reason the compose files refuse `qdrant:latest`.

**The digest in `docker/pod/IMAGE.lock` is the single source of truth for what
a pod session pulls.**

## What CI checks — and what it does not

**CI does not build the image.**

It used to, and compared the digest it got against the committed lock. That
check cannot pass in a steady state, because the build is not byte
reproducible. Run #1 and run #4 built the same Dockerfile from the same
`requirements.txt`; the base resolved identically both times
(`sha256:c7ff5829…`) and the results still differed:

    run #1   sha256:81567d58…
    run #4   sha256:12bd6a3e…

Our own apt and pip layers fetch from services that do not promise
byte-identical responses over time, and layer metadata carries build timestamps
regardless. Neither digest is wrong. The committed one names an image that
exists, was pushed, and has been pulled and run by two pod sessions — task 017c
proved Postgres starts on it — so run #4 put a red tick next to a perfectly
good image, on every push.

Rebuild-to-compare answers *"are these bytes reproducible"*. They are not, and
were never going to be. So CI asks the two questions that actually matter:

| check | question | fails when |
|---|---|---|
| **pullable** | does the registry still serve the digest the lock names? | the digest is gone, unreadable, or the registry errors |
| **co-change** | did a commit that changed the recipe also change the pin? | a build input moved and `IMAGE.lock` did not move in the same range |

Pullability is the only question whose answer changes what a session does — a
session pins that digest, so if it cannot be served, no session can start. It
reads the manifest and pulls no layers, so it is cheap enough for every push:
the image is gigabytes, the manifest is one request.

It tries `docker buildx imagetools inspect --raw` first and falls back to
`docker manifest inspect`, because the older command cannot read an **OCI**
manifest. Measured on Docker 20.10.17, against a public image that plainly
exists:

    $ docker manifest inspect alpine:latest
    unsupported manifest media type and no default available:
        application/vnd.oci.image.manifest.v1+json

Our image is built by buildx and pushed to GHCR, so its manifest is OCI too. A
check that depended on the client's manifest-format support would have gone red
for a reason that has nothing to do with whether a session can start — the same
class of false red this redesign exists to remove.

Co-change is what keeps the pin honest. Not *"does a rebuild reproduce it"* but
*"did whoever changed the recipe re-lock what it produces"*.

The logic lives in `oneground/pod/imagecheck.py` and is unit-tested, rather
than existing only as YAML that is exercised by being run.

## What counts as a build input

Derived from the Dockerfile, not declared, so it cannot drift from what the
build actually reads:

    python -m oneground.pod.imagecheck inputs
    docker/pod/Dockerfile
    requirements.txt

The Dockerfile itself, plus every path it `COPY`s or `ADD`s from the build
context. `--from=` copies and remote `ADD` URLs are excluded: neither reads a
file in this repository.

It is deliberately **not** `docker/pod/**`. The session scripts that sync at run
time — `corpora/run_verify_pod.sh`, `restart_engine.sh` and the like — are not
in the image and cannot change its bytes. Commit `696dd03` touched only those
and fired an 18-minute build for nothing. The workflow's `paths:` filter matches
the derived set (plus the workflow file itself, so that editing the check runs
the check), and a test asserts the two agree — a new `COPY` source that nobody
adds to the workflow fails the suite rather than silently escaping the check.

`docker/pod/IMAGE.lock` is not a build input either. It is the build's output,
recorded.

## Rebuilding and re-locking

Local and deliberate, because the digest has to be copied into the lock by the
person who changed the recipe, in the same commit.

    bash docker/pod/rebuild.sh

That builds, pushes, reads the digest **the registry assigned** (not the local
image id, which is a different number), writes it into the lock in place —
keeping every comment — and verifies the registry serves it. Then:

    git add docker/pod/Dockerfile requirements.txt docker/pod/IMAGE.lock
    git commit

Both in one commit. Splitting them fails the co-change check, which is the
point of the check.

To check the Dockerfile builds without touching the registry or the lock:

    DRY_RUN=1 bash docker/pod/rebuild.sh

A local build has no registry digest, so there is nothing to lock.

Requires `docker` and a registry login with write access:

    echo "$GHCR_TOKEN" | docker login ghcr.io -u <you> --password-stdin

## When the lock has no digest

Two cases, and they are different.

**Bootstrap** — the image has never been built. The lock carries no digest, the
pullability check warns and passes, and nothing is pinned yet. This branch was
reached and verified by run #4. With a digest present it is unreachable.

**A verify session** — `oneground verify` **refuses to start**:

    docker/pod/IMAGE.lock names no digest, so there is no pre-baked pod
    image to run.

It does not fall back to the base tag on its own. A session on the base image
has no Postgres, no pgvector, no Qdrant and no venv; it would install them at
run time, and when that went wrong it would present as an environment fault
several minutes in — which is exactly the failure mode the pre-baked image
exists to remove, and the one that cost two pods in task 015. A log line in a
pod session's output is easy to miss; a refusal before anything is created is
not.

The base image is still available, but it has to be **named**, so that it
appears in the receipt as something a person chose:

```yaml
verify:
  image: runpod/pytorch:1.1.0-cu1300-torch291-ubuntu2404
```

That value is `POD_IMAGE` in `oneground/verify/__init__.py` and
`fallback_image` in the lock; a test asserts the two agree, so the documented
escape hatch cannot drift from the code.

An explicitly named `verify.image` always wins, digest or no digest — someone
naming an image means it.

## Reading the lock

    image=ghcr.io/shamiksaharcciit-oss/oneground-pod
    digest=sha256:81567d58…
    tag=6641737
    reference=ghcr.io/shamiksaharcciit-oss/oneground-pod@sha256:81567d58…

`reference` is what a session spec uses and what `pod plan` prints. The `tag`
is recorded only so a digest can be traced back to the commit that built it —
nothing references the tag, and nothing should.

`oneground/pod/image.py` reads this file. Its one rule: a missing digest is
never a reason to fall back to a tag. `reference()` raises instead.
