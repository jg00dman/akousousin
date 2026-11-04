#!/bin/bash
set -Eeuo pipefail
project_dir=$(pwd)
wine_repository=${WINE_REPOSITORY:-https://github.com/FaithLife-Community/wine.git}
wine_base=${WINE_BASE:-3b19eb0e45ac5f57301073fc9e721cac7829dc93}
wine_version=${WINE_VERSION:-11.21-logos}
jobs=${BUILD_JOBS:-$(nproc)}
[[ "$jobs" =~ ^[1-9][0-9]*$ ]] || { echo 'BUILD_JOBS must be a positive integer' >&2; exit 2; }
# No CI desktop dialogs or optional runtime downloads. Piper stays external.
export WINEDLLOVERRIDES="mscoree,mshtml=;${WINEDLLOVERRIDES:-}"
export WINEDEBUG=${WINEDEBUG:--all}
export PYTHONUNBUFFERED=1
export WINE_SRC="$project_dir/wine-src" WINE_BUILD="$project_dir/wine-build"
export WINE="$WINE_BUILD/wine" WINEPREFIX="$project_dir/build/ci-prefix"
image="wine-akousousin-piper-${wine_version}-x86_64.AppImage"
share="$project_dir/AppDir/usr/share/akousousin"
mkdir -p build dist
stage=${1:-setup}
fail_stage() {
    local result=$?
    echo "::error::Stage $stage failed (exit $result)"
    exit "$result"
}
trap fail_stage ERR
run_stage() {
    stage=$1
    local limit=$2
    shift 2
    local started=$SECONDS
    echo "::group::$stage ($(date -u +%FT%TZ), limit $limit)"
    # Wine services can retain inherited stdout after wineboot exits. Stream
    # the log independently so those background processes cannot hold a pipe
    # open past the command's timeout or turn a completed command into a hang.
    local log="$project_dir/build/$stage.log"
    local command_pid tail_pid result
    : > "$log"
    timeout --signal=TERM --kill-after=30s "$limit" "$@" > "$log" 2>&1 &
    command_pid=$!
    tail --pid="$command_pid" -n +1 -f "$log" &
    tail_pid=$!
    if wait "$command_pid"; then result=0; else result=$?; fi
    wait "$tail_pid"
    if [ "$result" -ne 0 ]; then return "$result"; fi
    echo "Completed $stage in $((SECONDS - started)) seconds"
    echo '::endgroup::'
}


# Validate the original Piper patch beneath the additive write fix without
# touching source timestamps or the real Git index of a cached build.
verify_piper_patch() {
    local patch_check_dir
    if git -C wine-src apply --reverse --check "$project_dir/patches/wine-piper-site-write.patch" 2>/dev/null; then
        patch_check_dir=$(mktemp -d)
        if ! (
            export GIT_INDEX_FILE="$patch_check_dir/index"
            git -C wine-src read-tree HEAD
            git -C wine-src add --all -- dlls/sapi
            if git -C wine-src apply --cached --reverse --check "$project_dir/patches/wine-piper-lifecycle.patch" 2>/dev/null; then
                git -C wine-src apply --cached --reverse "$project_dir/patches/wine-piper-lifecycle.patch"
            fi
            git -C wine-src apply --cached --reverse "$project_dir/patches/wine-piper-site-write.patch"
            git -C wine-src apply --cached --reverse --check "$project_dir/patches/wine-piper.patch"
        ); then
            rm -rf -- "$patch_check_dir"
            return 1
        fi
        rm -rf -- "$patch_check_dir"
    else
        git -C wine-src apply --reverse --check "$project_dir/patches/wine-piper.patch"
    fi
}

case "${1:-}" in
    source)
if [ -d wine-src/.git ]; then
    cached_base=$(git -C wine-src rev-parse HEAD)
    # Migrate the one known async candidate checkpoint; never accept arbitrary
    # cached source edits. Only these exact reversible patches are supported.
    if git -C wine-src apply --reverse --check "$project_dir/scripts/ci/previous-piper-http.patch" 2>/dev/null; then
        git -C wine-src apply --reverse "$project_dir/scripts/ci/previous-piper-http.patch"
    fi
    verify_piper_patch
    if [ "$cached_base" != "$wine_base" ]; then
        # This one inspected transition retains identical configure inputs and
        # SAPI source. Cache lookup also requires the same toolchain and recipe.
        case "$cached_base:$wine_base" in
            2528aff26208257fdbf980666a4f0e66d47563ce:9a962f8799c79149af0be85d8d8f7b92951c1cc5) ;;
            9a962f8799c79149af0be85d8d8f7b92951c1cc5:3b19eb0e45ac5f57301073fc9e721cac7829dc93) ;;
            *) echo 'Unsupported cached Wine source transition' >&2; exit 1 ;;
        esac
        git -C wine-src fetch --depth=64 "$wine_repository" "$wine_base"
        git -C wine-src merge-base --is-ancestor "$cached_base" FETCH_HEAD
        git -C wine-src diff --exit-code "$cached_base" FETCH_HEAD -- \
            configure configure.ac Makefile.in tools dlls/sapi
        if [ "$wine_base" = 3b19eb0e45ac5f57301073fc9e721cac7829dc93 ]; then
            expected_changes=$(printf '%s\n' dlls/wined3d/context_gl.c dlls/wined3d/swapchain.c dlls/wined3d/wined3d_private.h)
            test "$(git -C wine-src diff --name-only "$cached_base" FETCH_HEAD)" = "$expected_changes"
            test "$(git -C wine-src rev-list --count "$cached_base"..FETCH_HEAD)" = 2
        fi
        # Checkout updates only changed tracked files and retains the nonoverlapping
        # Piper edits. Preserve object files so make follows the changed dependencies.
        git -C wine-src checkout --detach FETCH_HEAD
        test "$(git -C wine-src rev-parse HEAD)" = "$wine_base"
        verify_piper_patch
        echo 'Advanced verified cached Wine source to the pinned Logos tip; using incremental make'
    else
        echo 'Reusing matching patched Wine source'
    fi
else
git init wine-src
git -C wine-src remote add origin "$wine_repository"
git -C wine-src fetch --depth=1 origin "$wine_base"
git -C wine-src checkout --detach FETCH_HEAD
test "$(git -C wine-src rev-parse HEAD)" = "$wine_base"
git -C wine-src apply --check "$project_dir/patches/wine-piper.patch"
git -C wine-src apply "$project_dir/patches/wine-piper.patch"
fi
if git -C wine-src apply --reverse --check "$project_dir/patches/wine-sapi-enum-values.patch" 2>/dev/null; then
    echo 'Reusing SAPI value enumeration implementation'
else
    git -C wine-src apply --check "$project_dir/patches/wine-sapi-enum-values.patch"
    git -C wine-src apply "$project_dir/patches/wine-sapi-enum-values.patch"
fi
if git -C wine-src apply --reverse --check "$project_dir/patches/wine-piper-site-write.patch" 2>/dev/null; then
    echo 'Reusing System.Speech PCM write compatibility fix'
else
    git -C wine-src apply --check "$project_dir/patches/wine-piper-site-write.patch"
    git -C wine-src apply "$project_dir/patches/wine-piper-site-write.patch"
fi
if git -C wine-src apply --reverse --check "$project_dir/patches/wine-piper-lifecycle.patch" 2>/dev/null; then
    echo 'Reusing cancellable and bounded Piper HTTP transport'
else
    git -C wine-src apply --check "$project_dir/patches/wine-piper-lifecycle.patch"
    git -C wine-src apply "$project_dir/patches/wine-piper-lifecycle.patch"
fi
        ;;
    configure)
mkdir -p wine-build
if [ -f wine-build/.akousousin-configured ]; then
    echo 'Reusing configured build from matching toolchain/source cache'
else
    cd wine-build
    run_stage configure 10m bash "$project_dir/scripts/ci/configure-wine.sh"
    if grep -q 'No sound system was found' ../build/configure.log; then
        echo 'Audio support is required for this desktop test build.' >&2
        exit 1
    fi
    touch .akousousin-configured
fi
        ;;
    compile)
echo "Runner: $(nproc) CPUs; build jobs: $jobs"
free -h
cd wine-build
run_stage compile 120m make -j"$jobs"
        ;;
    install)
cd wine-build
run_stage install 10m make install DESTDIR="$project_dir/AppDir"
        ;;
    probes)
run_stage probes 5m bash scripts/build-probes.sh
        ;;
    build-tests)
mkdir -p "$WINEPREFIX"
touch "$WINEPREFIX/.akousousin-test-prefix"
run_stage integration 10m xvfb-run -a bash scripts/test-wine.sh
grep -q '^Ran 13 tests in ' build/integration.log
grep -qx 'OK' build/integration.log
run_stage failure-recovery 5m xvfb-run -a python3 tests/test_failures.py
run_stage enum-values 2m xvfb-run -a "$WINE" "$project_dir/build/token-enum-probe.exe"
        ;;
    assemble)
share="$project_dir/AppDir/usr/share/akousousin"
mkdir -p "$share/scripts" "$project_dir/AppDir/usr/share/licenses/akousousin"
cp build/sapi-probe.exe "$share/"
cp scripts/register-voice.py "$share/scripts/"
cp scripts/ci/AppRun AppDir/AppRun
chmod +x AppDir/AppRun
cp LICENSE AppDir/usr/share/licenses/akousousin/LGPL-2.1.txt
cp wine-src/COPYING.LIB AppDir/usr/share/licenses/akousousin/Wine-COPYING.LIB
cp scripts/ci/type2-runtime.LICENSE AppDir/usr/share/licenses/akousousin/AppImage-runtime-MIT.txt
cp scripts/ci/WINE-SOURCE.md "$share/"
cat > "$share/BUILD-INFO.txt" <<EOF
Experimental Akousousin Piper SAPI engine
Package version: $wine_version
Wine source version: $(cat wine-src/VERSION)
Wine source repository: $wine_repository
Wine source commit: $wine_base
Wine upstream base before the 17 Logos branch commits: 2528aff26208257fdbf980666a4f0e66d47563ce
Piper patch SHA256: $(sha256sum patches/wine-piper.patch | cut -d' ' -f1)
SAPI enumeration patch SHA256: $(sha256sum patches/wine-sapi-enum-values.patch | cut -d' ' -f1)
HTTP lifecycle patch SHA256: $(sha256sum patches/wine-piper-lifecycle.patch | cut -d' ' -f1)
PCM write patch SHA256: $(sha256sum patches/wine-piper-site-write.patch | cut -d' ' -f1)
Akousousin revision: $(git rev-parse HEAD)
Architecture: x86-64 Windows applications only; no WoW64/32-bit support
Built on Ubuntu 22.04; requires glibc 2.35 or newer and normal Wine host libraries.
Piper and voice models are NOT bundled in Wine.
Real neural synthesis is checked separately before publication; see real-packaged-piper.log.
EOF
cat > AppDir/akousousin.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=Wine Akousousin Piper Test
Exec=AppRun
Icon=akousousin
Categories=Utility;
EOF
cat > AppDir/akousousin.svg <<'EOF'
<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128"><rect width="128" height="128" rx="24" fill="#263b58"/><path d="M22 50h19l24-20v68L41 78H22z" fill="#fff"/><path d="M81 43q29 21 0 42M90 28q47 36 0 72" fill="none" stroke="#70d6cf" stroke-width="7"/></svg>
EOF

        ;;
    appimage)
# Freeze the official runtime downloaded over verified HTTPS. A changed release
# asset fails verification rather than silently changing the executable runtime.
stage=appimage
echo "::group::Create AppImage ($(date -u +%FT%TZ))"
curl --fail --location --retry 3 --connect-timeout 30 --max-time 180 \
    https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64 \
    -o build/appimage-runtime
echo '617aa77314d57c8b8e4fae9c3f0b35af7b30d5529cb69e98f64f92510ed98a46  build/appimage-runtime' | sha256sum --check
mksquashfs AppDir build/appdir.squashfs -noappend -root-owned -comp gzip -processors "$jobs"
image="wine-akousousin-piper-${wine_version}-x86_64.AppImage"
cat build/appimage-runtime build/appdir.squashfs > "dist/$image"
chmod +x "dist/$image"
echo '::endgroup::'
        ;;
    package-tests)
run_stage appimage-smoke 2m env APPIMAGE_EXTRACT_AND_RUN=1 "dist/$image" --akousousin-info
printf '%s\n' '{"audio":{"sample_rate":22050}}' > build/test-voice.onnx.json
export WINEPREFIX="$project_dir/build/package-prefix"
run_stage appimage-register 3m env APPIMAGE_EXTRACT_AND_RUN=1 xvfb-run -a "dist/$image" \
    --akousousin-register "$project_dir/build/test-voice.onnx.json"
run_stage packaged-integration 10m env WINE="$project_dir/AppDir/AppRun" \
    xvfb-run -a python3 tests/test_integration.py
grep -q '^Ran 13 tests in ' build/packaged-integration.log
grep -qx 'OK' build/packaged-integration.log
touch "$WINEPREFIX/.akousousin-test-prefix"
run_stage packaged-failure-recovery 5m env WINE="$project_dir/AppDir/AppRun" xvfb-run -a python3 tests/test_failures.py
run_stage packaged-enum-values 2m xvfb-run -a "$project_dir/AppDir/AppRun" "$project_dir/build/token-enum-probe.exe"
mkdir -p build/appimage-bin
ln -sf "$project_dir/dist/$image" build/appimage-bin/wineserver
run_stage appimage-wineserver-dispatch 1m env APPIMAGE_EXTRACT_AND_RUN=1 "$project_dir/build/appimage-bin/wineserver" -k
        ;;
    real-piper-test)
run_stage real-packaged-piper 7m xvfb-run -a python3 tests/packaged_piper_smoke.py "$project_dir/dist/$image"
        ;;
    archives)
tar -C AppDir -cJf "dist/wine-akousousin-piper-${wine_version}-x86_64.tar.xz" .
tar --exclude=.git -cJf "dist/wine-akousousin-piper-${wine_version}-source.tar.xz" wine-src
cp patches/wine-piper.patch patches/wine-logos-11.21.patch patches/wine-sapi-enum-values.patch patches/wine-piper-site-write.patch patches/wine-piper-lifecycle.patch dist/
cp scripts/ci/WINE-SOURCE.md dist/WINE-SOURCE.md
cp scripts/ci/APPIMAGE-TESTING.md dist/APPIMAGE-TESTING.md
cp scripts/ci/APPIMAGE-TESTING.md build/RELEASE-NOTES.md
cp "$share/BUILD-INFO.txt" dist/
cp build/integration.log build/failure-recovery.log build/packaged-failure-recovery.log build/real-packaged-piper.log dist/
cp build/real-piper/real-piper-sapi.wav dist/real-piper-sapi.wav
cp build/packaged-integration.log build/enum-values.log build/packaged-enum-values.log dist/
(
    cd dist
    sha256sum ./* > SHA256SUMS
)
cat "$share/BUILD-INFO.txt" >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
cat build/integration.log >> "${GITHUB_STEP_SUMMARY:-/dev/null}"

        ;;
    *) echo 'Select a stage: source configure compile install probes build-tests assemble appimage package-tests archives' >&2; exit 2 ;;
esac
