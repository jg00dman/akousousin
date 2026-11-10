<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Command-line speech registration

Wine/SAPI registration works from the panel or CLI. Run registration from the AKS
installation you intend to keep. The engine reads an explicit `Launcher` REG_SZ
from each registered SAPI voice token; it does not guess a default AppImage path.
The command contains `--api-start` and the absolute profile settings path.

For an installed standalone tar bundle:

```sh
~/.local/bin/akousousin --wine-prefix "$HOME/.wine" \
  --wine "/absolute/path/to/Wine.AppImage" --install-only
```

For AKS AppImage:

```sh
"$HOME/.local/share/Akousousin/Akousousin-x86_64.AppImage" \
  --wine-prefix "$HOME/.wine" --wine "/absolute/path/to/Wine.AppImage" --install-only
```

Substitute the actual initialized 64-bit prefix and Wine executable. Close its
applications first. An installed speech voice is needed for usable voice tokens.
`--settings /absolute/path/settings.json` selects another profile. `--install-only`
performs registration without opening the panel; `--install-speech-dispatcher`
separately configures Linux speech output and is not Wine registration.

When moving between tar and AppImage, reapply registration using the destination
installation. To refresh saved active registrations using the current package:

```sh
~/.local/bin/akousousin --refresh-registrations
```

To correct a stale Wine executable path, rerun the full `--wine-prefix ... --wine
... --install-only` command with its current path. Missing saved Wine executables
are warned about and skipped during refresh; their records remain for repair.

## Cold start and the Wine environment

The registered Unix launcher clears inherited Wine AppImage identity and private
library variables before running AKS. The tar runtime also requires its own
AppImage package marker before treating APPIMAGE as its executable. This fixes
the tar cold-start failure caused by inheriting a different application's
APPIMAGE. Re-register existing installations to replace the old launcher command.
This source fix follows beta 10; the beta 10 tar download does not contain it.

After registration, quit AKS, then request speech from Logos. This verifies DLL
cold start; successful speech while AKS is already running does not verify the
launcher. Keep the installed AKS executable in place. DLLs that an application
has already loaded may require that application to restart after registration.
