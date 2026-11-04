#!/bin/bash
# Run each visible workflow stage in the same immutable build environment.
set -euo pipefail
: "${CI_IMAGE_ID:?Set the verified build environment image ID}"
docker run --rm --init \
    --user "$(id -u):$(id -g)" \
    --volume "$PWD:$PWD" --workdir "$PWD" \
    --env HOME=/tmp/akousousin-home \
    --env WINE_REPOSITORY --env WINE_BASE --env WINE_VERSION \
    "$CI_IMAGE_ID" bash -c 'mkdir -p "$HOME"; exec bash scripts/ci/build-appimage.sh "$@"' -- "$@"
