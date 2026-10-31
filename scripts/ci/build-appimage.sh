#!/bin/bash
set -euo pipefail
project_dir=$(pwd)
wine_base=${WINE_BASE:-2528aff26208257fdbf980666a4f0e66d47563ce}
wine_version=${WINE_VERSION:-11.21}
jobs=${BUILD_JOBS:-2}
mkdir -p build dist
git init wine-src
git -C wine-src remote add origin https://github.com/jg00dman/wine.git
git -C wine-src fetch --depth=1 origin "$wine_base"
git -C wine-src checkout --detach FETCH_HEAD
test "$(git -C wine-src rev-parse HEAD)" = "$wine_base"
git -C wine-src apply --check "$project_dir/patches/wine-piper.patch"
git -C wine-src apply "$project_dir/patches/wine-piper.patch"
mkdir wine-build
(
    cd wine-build
    ../wine-src/configure --enable-win64 --prefix=/usr --without-oss --disable-winemenubuilder \
        CFLAGS='-O2' CXXFLAGS='-O2' > ../build/configure.log 2>&1
    if grep -q 'No sound system was found' ../build/configure.log; then
        echo 'Audio support is required for this desktop test build.' >&2
        exit 1
    fi
    make -j"$jobs" > ../build/compile.log 2>&1
    make install DESTDIR="$project_dir/AppDir" > ../build/install.log 2>&1
)
export WINE_SRC="$project_dir/wine-src" WINE_BUILD="$project_dir/wine-build"
bash scripts/build-probes.sh
export WINE="$WINE_BUILD/wine" WINEPREFIX="$project_dir/build/ci-prefix"
xvfb-run -a bash scripts/test-wine.sh > build/integration.log 2>&1

share="$project_dir/AppDir/usr/share/opensapi"
mkdir -p "$share/scripts" "$project_dir/AppDir/usr/share/licenses/opensapi"
cp build/sapi-probe.exe "$share/"
cp scripts/register-voice.py "$share/scripts/"
cp scripts/ci/AppRun AppDir/AppRun
chmod +x AppDir/AppRun
cp LICENSE AppDir/usr/share/licenses/opensapi/LGPL-2.1.txt
cp wine-src/COPYING.LIB AppDir/usr/share/licenses/opensapi/Wine-COPYING.LIB
cp scripts/ci/type2-runtime.LICENSE AppDir/usr/share/licenses/opensapi/AppImage-runtime-MIT.txt
cat > "$share/BUILD-INFO.txt" <<EOF
Experimental OpenSAPI Piper SAPI engine
Wine version: $wine_version
Wine base: $wine_base
OpenSAPI revision: $(git rev-parse HEAD)
Architecture: x86-64 Windows applications only; no WoW64/32-bit support
Built on Ubuntu 22.04; requires glibc 2.35 or newer and normal Wine host libraries.
Piper and voice models are NOT bundled. No real neural synthesis has been tested in CI.
EOF
cat > AppDir/opensapi.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=Wine OpenSAPI Piper Test
Exec=AppRun
Icon=opensapi
Categories=Utility;
EOF
cat > AppDir/opensapi.svg <<'EOF'
<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128"><rect width="128" height="128" rx="24" fill="#263b58"/><path d="M22 50h19l24-20v68L41 78H22z" fill="#fff"/><path d="M81 43q29 21 0 42M90 28q47 36 0 72" fill="none" stroke="#70d6cf" stroke-width="7"/></svg>
EOF

# Freeze the official runtime downloaded over verified HTTPS. A changed release
# asset fails verification rather than silently changing the executable runtime.
curl --fail --location --retry 3 \
    https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64 \
    -o build/appimage-runtime
echo '617aa77314d57c8b8e4fae9c3f0b35af7b30d5529cb69e98f64f92510ed98a46  build/appimage-runtime' | sha256sum --check
mksquashfs AppDir build/appdir.squashfs -noappend -root-owned -comp gzip -processors "$jobs"
image="wine-opensapi-piper-${wine_version}-x86_64.AppImage"
cat build/appimage-runtime build/appdir.squashfs > "dist/$image"
chmod +x "dist/$image"
APPIMAGE_EXTRACT_AND_RUN=1 "dist/$image" --opensapi-info > build/appimage-smoke.log 2>&1

# Check the packaged runtime and embedded C sample, not just the build-tree DLL.
printf '%s\n' '{"audio":{"sample_rate":22050}}' > build/test-voice.onnx.json
export WINEPREFIX="$project_dir/build/package-prefix"
APPIMAGE_EXTRACT_AND_RUN=1 xvfb-run -a "dist/$image" --opensapi-register "$project_dir/build/test-voice.onnx.json" \
    > build/appimage-register.log 2>&1
WINE="$project_dir/AppDir/AppRun" xvfb-run -a python3 tests/test_integration.py \
    > build/packaged-integration.log 2>&1

tar -C AppDir -cJf "dist/wine-opensapi-piper-${wine_version}-x86_64.tar.xz" .
tar --exclude=.git -cJf "dist/wine-opensapi-piper-${wine_version}-source.tar.xz" wine-src
cp patches/wine-piper.patch dist/
cp scripts/ci/APPIMAGE-TESTING.md dist/APPIMAGE-TESTING.md
cp scripts/ci/APPIMAGE-TESTING.md build/RELEASE-NOTES.md
cp "$share/BUILD-INFO.txt" dist/
cp build/integration.log dist/
cp build/packaged-integration.log dist/
(
    cd dist
    sha256sum ./* > SHA256SUMS
)
cat "$share/BUILD-INFO.txt" >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
cat build/integration.log >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
