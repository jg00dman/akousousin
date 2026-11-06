<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Akousousin licensing

Copyright 2026 John Goodman.

Akousousin's original project source is licensed under **GPL-3.0-or-later**,
except for its separately licensed SAPI engine implementation and API headers,
which are licensed under **LGPL-2.1-or-later**.

| Material | Licence |
| --- | --- |
| Original application, Python backend, installers, tests, examples, build tools, workflows and documentation | GPL-3.0-or-later; see [LICENSE](https://github.com/jg00dman/akousousin/blob/main/LICENSE) |
| Original SAPI engine C files and `engine/engine.h` | LGPL-2.1-or-later; see [LGPL text](https://github.com/jg00dman/akousousin/blob/main/LICENSES/LGPL-2.1-or-later.txt) |
| Wine-derived `engine/include/sapiddk.h` and `engine/include/sperror.h` | Their retained Wine notices and LGPL-2.1-or-later terms apply |
| Wine patches in `patches/` and `scripts/ci/previous-piper-http.patch` | Their existing Wine/source terms and notices apply |
| Piper voice catalogue and its upstream catalogue notice in `standalone/resources/` | The retained upstream MIT declaration applies; individual models have their own terms |
| Python, Whisper and AppImage runtime licence files | Their respective upstream terms and notices apply |
| External libraries, Wine, Piper, models and other downloaded dependencies | Their own upstream licences; see the notices accompanying each distribution |

File-level SPDX identifiers identify the applicable licence for original source.
The original JSON voice-download manifest uses an adjacent `.license` file so the
JSON data stays valid. Its licence does not change the terms of referenced models.
Existing upstream copyright notices are retained. No John Goodman copyright claim
is added to imported Wine headers, patches, licence texts or catalogue material.

## Distribution notices

The standalone AppImage and Windows ZIP include these files in `licenses/`:

- `Akousousin-GPL-3.0.txt`: the GPL text for original project code.
- `Engine-LGPL-2.1.txt`: the LGPL text for the SAPI component.
- `Akousousin-LICENSING.md`: this component-licensing explanation.
- Dependency and voice notices supplied by their upstream publishers.

The legacy Wine AppImage includes the project GPL text, the separate LGPL text,
Wine's `COPYING.LIB`, and the upstream runtime notice in its shared licence folder.
Standalone backend/recognition bundles carry the project GPL text and their
applicable upstream notices. Python distribution metadata declares GPL-3.0-or-later
for the original Python packages and includes their GPL licence text.

Matching project and dependency sources accompany binary distributions as described
in the package documentation. The SAPI DLL remains a separately licensed LGPL
component. This document does not replace or modify any third-party licence.
