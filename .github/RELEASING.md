<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Standalone beta publication

Main pushes build Linux and native Windows packages and run their packaged tests.
Linux also runs real Whisper inference. Publishing waits for both package jobs and
the engine job to succeed. Whisper branch trials remain separate prereleases with
a direct AppImage download.

Bump both `standalone/pyproject.toml` and `standalone/akousousin_app/__init__.py`,
update release notes and compatibility documentation, and include `[publish beta]`
in the explicitly approved main commit message to publish that beta after its
checks pass. Normal main pushes do not publish releases. Alternatively dispatch
Standalone Akousousin with `publish=true`, or use Publish tested standalone
Akousousin with a completed main run ID to reuse a checked build.

Release tags contain the version, run ID and attempt; existing releases are not
overwritten. Each published version must increase for the application's update
checker. The AppImage, Windows ZIP, corresponding sources, checksums and guides
are separate assets, so testers can download the program alone. Whisper model
weights remain outside the application package.
