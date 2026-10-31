# Prototype validation

The Wine changes are saved locally on `codex/piper-sapi-prototype`, commit
`b688f135551`. The OpenSAPI repository also carries the complete patch, so its
source backup is sufficient to reproduce the Wine edits at the base below.
These local commits have not been pushed to GitHub.

Validated in this cloud workspace against Wine commit
`2528aff26208257fdbf980666a4f0e66d47563ce` (11.21), x86-64 Linux, with a
MinGW-w64 GCC 14 compiler. The Wine source checkout contains the patch directly.

## Completed

* Built the modified `sapi.dll`, a matching targeted Wine runtime, and both C probes.
  No warnings were emitted for `piper.c`.
* Ran `tests/test_integration.py` through the real compiled Wine DLL:
  **13 tests passed**. HTTP/WAV failure cases include six separately executed
  subtests. The HTTP server supplies deterministic PCM, not neural speech.
* Ran Wine's `sapi_test.exe token`: **234 tests executed, zero failures,
  six existing TODO outcomes, zero skipped**. This includes the added DWORD
  persistence tests.
* Ran Wine's `sapi_test.exe tts`: **23 tests executed, zero failures,
  two skips due to no wave-output device**. Audio-dependent sections did not run.
* Confirmed `patches/wine-piper.patch` applies cleanly to an archived copy of the
  selected Wine HEAD and reverse-checks against the edited source tree.
* Installed `piper-tts[http]==1.8.0` in `/workspace/.piper-venv`.

The local compiler/parser packages are extracted below
`/workspace/.build-tools/root`; system packages were not changed. To use them:

```sh
export PATH=/workspace/.build-tools/root/usr/bin:$PATH
export BISON_PKGDATADIR=/workspace/.build-tools/root/usr/share/bison
export M4=/workspace/.build-tools/root/usr/bin/m4
```

The build is in `/workspace/build-wine`. Its headless configuration is:

```sh
/workspace/wine/configure --enable-win64 --without-x --without-wayland \
    --without-freetype --without-alsa --without-pulse
```

The targeted runtime also needs generated `include/all` and `nls/all`, the
`atl100` registrar, forwarded DLL dependencies, and the services/programs used
by prefix initialization. `runtime-targets.txt` and the build logs in that build
directory record the targets used. A normal full build supplies those targets.
This is not a desktop or complete AppImage build.

The successful suite used the marked disposable prefix
`/workspace/opensapi/build/test-prefix-v2`:

```sh
WINE=/workspace/build-wine/wine \
WINEPREFIX=/workspace/opensapi/build/test-prefix-v2 \
    sh scripts/test-wine.sh
```

Logs are retained in `build/integration.log`, `build/wine-token-tests.log`, and
`build/wine-tts-tests.log`. Build outputs and disposable prefixes are ignored by Git.

## Still unverified

The actual voice download failed with a proxy `403 Forbidden` for Hugging Face.
No real Piper TTS model was downloaded, no neural speech was synthesized, and no
audible playback was tested. The smoke-test runner itself was exercised against
the deterministic substitute; that does not establish real Piper speech works.

The network configuration draft now includes `huggingface.co`,
`cdn-lfs.huggingface.co`, `cdn-lfs-us-1.hf.co`, and `cas-bridge.xethub.hf.co`,
preserving the existing package-manager presets. The save succeeded, but it did
not activate or publish these changes. Review and save them in environment
settings, then publish the environment. Retry the model download after the policy
is applied and run the real-server steps and `scripts/smoke-piper.py` in the README.

Desktop playback, Logos, the VisualFBEditor sample, WoW64/32-bit execution, and
AppImage packaging have not been validated. No branch was pushed, workflow
dispatched, release published, or upstream PR submitted.
