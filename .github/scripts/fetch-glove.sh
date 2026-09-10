#!/usr/bin/env bash
# Fetch the ANN-Benchmarks GloVe HDF5 and refuse to proceed on the wrong bytes.
#
# The digest check is the point. The published reference values in
# fixtures/glove-100-angular.fixture.yaml were measured against one specific
# corpus; a silently re-uploaded upstream file would move every measured recall
# and look like a calibration drift in this tool rather than a change in the
# input. Better to fail loudly and make someone look.
set -euo pipefail

URL="${GLOVE_URL:-http://ann-benchmarks.com/glove-100-angular.hdf5}"
WANT="${GLOVE_SHA256:?GLOVE_SHA256 must be set}"
DEST="${GLOVE_DEST:-.cache/glove-100-angular.hdf5}"

mkdir -p "$(dirname "$DEST")"

if [ -f "$DEST" ]; then
  echo "cache hit: $DEST"
else
  echo "downloading $URL"
  curl -fsSL --retry 3 --retry-delay 5 -o "$DEST.part" "$URL"
  mv "$DEST.part" "$DEST"
fi

GOT="$(sha256sum "$DEST" | cut -d' ' -f1)"
if [ "$GOT" != "$WANT" ]; then
  echo "::error::corpus digest mismatch."
  echo "  expected $WANT"
  echo "  got      $GOT"
  echo "  The fixture's published reference values were measured against the"
  echo "  expected bytes. Refusing to calibrate against a different corpus:"
  echo "  every recall would move and it would read as drift in this tool."
  rm -f "$DEST"
  exit 1
fi
echo "corpus verified: $GOT"
