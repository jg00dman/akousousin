# Prototype validation

## Current Logos + Piper AppImage CI validation

[Run 41372784570](https://github.com/jg00dman/opensapi/actions/runs/41372784570)
succeeded for OpenSAPI commit `a43e304c12dc3b612f1a6d3b38fb72846def3bff` and
published [the Logos + Piper test release](https://github.com/jg00dman/opensapi/releases/tag/piper-test-41372784570-1).

* The full FaithLife-Community `logos-11.21` tip is pinned at
  `9a962f8799c79149af0be85d8d8f7b92951c1cc5`, including all 15 branch commits.
  Piper applies cleanly on top; no SAPI source was changed by the Logos branch.
* The existing Ubuntu 22.04 dependency image and compatible compiled Wine
  checkpoint were reused. The verified incremental source transition preserved
  Piper edits, unchanged file timestamps and build outputs. Incremental make
  completed in **13 seconds**; the build job completed in 12 minutes 26 seconds.
* All **13 build-tree and 13 packaged integration tests passed**, along with the
  AppImage extraction/version/registration checks. These use synthetic PCM.
* The downloaded AppImage/source digests and all published checksums were verified.
  All 16 Logos-modified source files in the release archive match the pinned
  branch byte-for-byte. Both patches and `WINE-SOURCE.md` are release assets.
* AppRun no longer disables `mscoree` globally. Local wrapper checks verified
  normal launches preserve native .NET overrides, while optional Mono/Gecko
  suppression is limited to explicit prefix initialization.

The user reported hearing real Piper speech on Kubuntu 26.04 with the preceding
Piper-only build. The combined Logos build still needs desktop startup and Read
Aloud testing in the user's existing Logos/.NET prefix. No model is bundled or
cleared for redistribution; no native .NET or Logos installation is bundled.
The architecture remains 64-bit only, without WoW64, and the Ubuntu 22.04 target
is unchanged. No Wine compilation was performed in the cloud workspace.

The original run's diagnostic artifact is now readable. It records `Wine build
complete` about 40 minutes after configuration, followed by successful install.
Its integration log was created but remained empty until cancellation. This
locates the long stall after compilation, during entry to the integration/setup
stage; the exact command cannot be established from those untraced logs.

## Earlier Piper-only AppImage CI validation

[Run 41365675371](https://github.com/jg00dman/opensapi/actions/runs/41365675371) succeeded for OpenSAPI commit
`bc62ec5633e8f73e5f1c5c73b542d69e81d0b121` and published
[the experimental test release](https://github.com/jg00dman/opensapi/releases/tag/piper-test-41365675371-1). It includes the AppImage, an AppDir
tarball, checksums, matching patched Wine source, the patch, and test instructions.

* All 13 integration tests passed against the build-tree Wine runtime.
* All 13 integration tests passed against packaged Wine, with AppImage extraction,
  version and voice-registration checks also passing.
* The Wine base is `2528aff26208257fdbf980666a4f0e66d47563ce` (11.21), with
  `patches/wine-piper.patch` applied during CI. No push to the Wine fork is needed.
* Fresh compilation took 19 minutes 58 seconds. Reusing its compatible checkpoint
  completed the compile step in one second. Dependency setup is cached separately;
  configuration, compilation, installation, tests and packaging are visible steps.
* A log-streaming pipe could wait on background Wine processes after a command
  exited. The corrected wrapper streams a file while tracking the command PID;
  local checks cover normal completion, nonzero exits, timeouts and inherited
  output handles. Both real integration runs then completed successfully.

These are deterministic synthetic-audio tests, not real Piper speech or audible
playback. Piper and voice models are not bundled. No model is cleared for
redistribution by this project. The package targets x86-64 Linux with glibc 2.35
or newer; Logos and WoW64/32-bit execution remain unverified. Wine was built only
in GitHub Actions, not in the current cloud workspace.

## Historical cloud-workspace validation

The following records describe the previous headless development environment.
Its local build paths and installed tools do not describe the current workspace.

The Wine changes are saved locally on `codex/piper-sapi-prototype`, commit
`b688f135551`. The OpenSAPI repository also carries the complete patch, so its
source backup is sufficient to reproduce the Wine edits at the base below.
The OpenSAPI branch, including the complete Wine patch and instructions, has now
been pushed to GitHub. Pushing the Wine branch itself was denied by GitHub; the
patch in OpenSAPI preserves those changes independently of this cloud workspace.

Validated in this cloud workspace against Wine commit
`2528aff26208257fdbf980666a4f0e66d47563ce` (11.21), x86-64 Linux, with a
MinGW-w64 GCC 14 compiler. The Wine source checkout contains the patch directly.

### Completed in the previous workspace

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

### Historical limitations and remaining checks

The actual voice download failed with a proxy `403 Forbidden` for Hugging Face.
No real Piper TTS model was downloaded, no neural speech was synthesized, and no
audible playback was tested. The smoke-test runner itself was exercised against
the deterministic substitute; that does not establish real Piper speech works.

The previous environment proposed Hugging Face download-host additions for a
real-model test. Those are not needed for the current AppImage CI workflow,
which does not download Piper or voice models.

Desktop playback, Logos, the VisualFBEditor sample, and WoW64/32-bit execution
remain unverified. AppImage packaging is now covered by the successful CI run
above. The initial run `41248009427` timed out; its diagnostic files locate the stall after installation, before any integration
test output, without identifying the exact setup command. No upstream PR has been submitted.
