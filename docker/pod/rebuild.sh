#!/usr/bin/env bash
#
# Rebuild the pod image, push it, and re-lock the digest. Task 017d.
#
# WHY THIS IS LOCAL AND NOT CI
# ----------------------------
# The build is not byte-reproducible. Run #1 and run #4 built the same
# Dockerfile from the same requirements.txt and produced different digests --
# the base resolved identically, but apt and pip fetch from services that do
# not promise byte-identical responses over time, and layer metadata carries
# build timestamps regardless.
#
# So CI cannot rebuild and compare: a correct lock would still disagree with a
# fresh build, and the red tick would sit next to a perfectly good image. CI
# checks two other things instead (see oneground/pod/imagecheck.py):
#
#   pullable    the locked digest still exists in the registry
#   co-change   whoever changed the recipe also re-locked what it produces
#
# The second is what makes this script necessary. Changing the Dockerfile or
# requirements.txt without running this will fail CI, by design: the pin has to
# be updated by the person who changed what it pins, in the same commit.
#
# USAGE
# -----
#     bash docker/pod/rebuild.sh                 # build, push, re-lock
#     DRY_RUN=1 bash docker/pod/rebuild.sh       # build only, no push, no lock
#
# Then commit the lock TOGETHER with the change that caused the rebuild:
#
#     git add docker/pod/Dockerfile docker/pod/IMAGE.lock
#     git commit
#
# Requires: docker, and a login to the registry with write access
# (`echo $GHCR_TOKEN | docker login ghcr.io -u <you> --password-stdin`).

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"

REGISTRY="${REGISTRY:-ghcr.io}"
OWNER="${OWNER:-shamiksaharcciit-oss}"
IMAGE="${IMAGE:-${REGISTRY}/${OWNER}/oneground-pod}"
DRY_RUN="${DRY_RUN:-}"

PY=.venv/bin/python
[ -x "$PY" ] || PY=.venv/Scripts/python.exe
[ -x "$PY" ] || { echo "ERROR: no venv at $REPO/.venv" >&2; exit 1; }

TAG="$(git rev-parse --short HEAD)"

echo "=============================================================="
echo "pod image rebuild"
echo "  repo    : $REPO"
echo "  image   : $IMAGE"
echo "  tag     : $TAG   (traceability only -- nothing references the tag)"
echo "  inputs  :"
"$PY" -m oneground.pod.imagecheck inputs | sed 's/^/              /'
echo "=============================================================="

# The tree must be clean, or the tag names a commit that does not describe
# what was built. The whole point of the lock is that the digest can be traced
# back to a recipe somebody can read.
if [ -n "$(git status --porcelain -- docker/pod/Dockerfile requirements.txt)" ]; then
    echo
    echo "NOTE: a build input is modified but not committed. The tag above"
    echo "      names HEAD, which is not what is about to be built. Commit the"
    echo "      Dockerfile change first, then run this, then amend the lock in."
    echo
fi

if [ -n "$DRY_RUN" ]; then
    echo "DRY_RUN set: building only, no push and no lock update."
    docker build -f docker/pod/Dockerfile -t "${IMAGE}:${TAG}" .
    echo
    echo "Built ${IMAGE}:${TAG} and stopped. A local build has no registry"
    echo "digest, so there is nothing to lock: the digest a session pins is"
    echo "the one the registry assigns on push."
    exit 0
fi

echo
echo "building and pushing ..."
# --iidfile gives the image id, which is NOT the registry digest. The digest a
# session pins is what the registry assigns, so it is read back from the push
# with `docker buildx imagetools inspect` rather than guessed from the build.
docker build -f docker/pod/Dockerfile -t "${IMAGE}:${TAG}" .
docker push "${IMAGE}:${TAG}"

DIGEST="$(docker buildx imagetools inspect "${IMAGE}:${TAG}" \
          --format '{{json .Manifest.Digest}}' 2>/dev/null | tr -d '"')"
if [ -z "$DIGEST" ]; then
    # Older docker without imagetools --format: fall back to the repo digest
    # docker records against the local image after a push.
    DIGEST="$(docker inspect --format '{{index .RepoDigests 0}}' \
              "${IMAGE}:${TAG}" | sed 's/.*@//')"
fi
case "$DIGEST" in
    sha256:*) ;;
    *) echo "ERROR: could not read a sha256 digest for ${IMAGE}:${TAG}" >&2
       echo "       got: ${DIGEST:-<empty>}" >&2
       exit 1 ;;
esac

echo
echo "pushed digest: $DIGEST"
echo
"$PY" -m oneground.pod.imagecheck relock \
    --image "$IMAGE" --digest "$DIGEST" --tag "$TAG"

echo
echo "Verifying the registry serves what was just locked ..."
"$PY" -m oneground.pod.imagecheck pullable

echo
echo "Now commit the lock with the change that caused the rebuild:"
echo "    git add docker/pod/Dockerfile requirements.txt docker/pod/IMAGE.lock"
echo "    git commit"
echo
echo "CI will check that the locked digest is pullable and that the lock moved"
echo "in the same range as the build inputs. It will NOT rebuild."
