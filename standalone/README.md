# OpenSAPI standalone beta

This package contains a standard 64-bit Windows COM speech engine DLL, a control
panel, and a local Waitress/Piper service. No voice model weights are redistributed in this package.
It does not contain a Wine runtime. Existing beta branches/main are unchanged.

Linux (x86-64, glibc 2.35+, same Ubuntu 22.04 target):

```
chmod +x OpenSAPI-x86_64.AppImage
APPIMAGE_EXTRACT_AND_RUN=1 ./OpenSAPI-x86_64.AppImage \
  --wine-prefix /absolute/path/to/existing/prefix \
  --wine /absolute/path/to/your/Wine.AppImage
```

The prefix must already be initialized and 64-bit. Close applications first.
This installs and opens the panel; add `--install-only` for a non-GUI install.
`--uninstall --wine-prefix ... --wine ...` restores original speech registration
and replaced DLLs. Voice downloads and panel preferences are retained.

The installer probes SAPI registry enumeration. Where the generic fix is missing,
a Wine-only compatibility sapi.dll is supplied for Wine 11.21, with its exact
matching source. `--wine-compat` forces that compatibility path for testing. Other
Wine versions with the missing method require their own compatible core DLL;
the installer refuses to guess. A launcher forcing `sapi=b` overrides prefix
registry preferences; remove that forced override when a compatibility DLL is
required. Native Windows sapi.dll is never replaced.

Windows: extract the ZIP and run opensapi.exe for the panel. Run it from an
administrator terminal with `--install --install-only` to register voice tokens;
then use the panel without administrator rights. `--uninstall` restores saved
registration. The engine is standard Windows/SAPI code and uses only public
Win32 APIs. This beta is 64-bit only.

For an existing Logos setup:

1. Close Logos and launch the AppImage with the prefix/Wine flags above.
2. In **Voice library**, use **Import local model** for your existing `.onnx`
   (its matching `.onnx.json` must be alongside it), or review/download a voice.
3. Select the installed voice and click **Make default**.
4. In **Settings**, click **Install / apply voice registration**.
5. In **Overview**, click **Start server**, then **Play sample**. Leave the
   service running and launch Logos with the same Wine executable/AppImage.
6. Remove a launcher’s forced `sapi=b` override if using the compatibility DLL.
   Prefix registration then selects `native,builtin` automatically.

To reopen the configuration app later, run it without installation flags:

```
APPIMAGE_EXTRACT_AND_RUN=1 ./OpenSAPI-x86_64.AppImage
```

The OpenSAPI AppImage installs speech support; it is not a replacement Wine
launcher. Keep using your working Logos Wine package. You can close the panel
while its server runs, reopen it later, and choose **Stop server**.

After installation, import an existing voice or review and download a voice from
its upstream source. Engine-only installation registers no unusable placeholder
voice and leaves the existing speech defaults unchanged until a voice is selected.

The panel offers Start/Stop, preview, searchable language/voice catalogue, local
model import, default voice, speed, volume and Piper noise controls. It does not
advertise unsupported pitch adjustment. Preferences are saved per user. Model
and runtime files required by a background server are copied outside ephemeral
AppImage mounts; closing the panel can leave its server running. Only a server
with this profile's private control token can be stopped by this panel.

One inference worker/model is loaded at a time to limit memory use. Standard
SAPI language hints can select language preferences; a manual book-language
selection is also available. This does not infer the language of isolated words
or promise that Logos supplies language markers. Different model sample rates
are converted to the format negotiated with SAPI. Missing/unavailable voices,
HTTP failures and inference timeouts return errors rather than silent success.

The pinned catalogue preserves upstream metadata. LJSpeech has the project's
reviewed repository-MIT/public-domain-data provenance. Other voices may have
non-commercial, attribution or additional conditions: review their individual
model/dataset terms before downloading. A catalogue entry is not a blanket
redistribution approval. Downloaded cards and provenance are retained. Latin
requires an appropriate model and is not invented or substituted in the catalogue.

DLL installation stores a recovery record in the selected prefix's
`drive_c/Program Files/OpenSAPI/`. It preserves prior defaults/registration and
any replaced DLLs. It refuses to uninstall over subsequently modified DLLs.
Prefix selection is explicit and no Windows credentials are collected or bundled.

Source licensing: engine LGPL-2.1-or-later; panel/service GPL-3.0-or-later;
Piper/eSpeak and embedded-dependency notices are in licenses/. The accompanying
sources archive includes our source/build scripts and the exact compatibility
Wine, Piper and eSpeak sources. Windows and Wine behavior are tested separately;
passing WAV checks does not establish audible playback or every Logos behavior.

Optional Arabic/Hebrew preprocessing model weights are also excluded from the
program-only distribution; those languages are marked unavailable in this beta
until a separate resource-download/licence path is provided. Other catalogue
entries remain subject to their individual model licences.
