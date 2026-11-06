<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 John Goodman
-->

# Wine source for the Logos + Piper test build

Repository: https://github.com/FaithLife-Community/wine
Branch inspected: `logos-11.21`
Pinned branch tip: `3b19eb0e45ac5f57301073fc9e721cac7829dc93`
Upstream Wine 11.21 base: `2528aff26208257fdbf980666a4f0e66d47563ce`

The complete branch tip is fetched, then `patches/wine-piper.patch` and
`patches/wine-sapi-enum-values.patch`, `patches/wine-piper-site-write.patch`
and `patches/wine-piper-lifecycle.patch` are applied.
All 17 branch commits are included; no selection or cherry-picking is performed.
The branch changes no SAPI files, and the Piper patch applies cleanly on this tip.
A later branch update requires explicitly changing the pinned source commit.

`wine-logos-11.21.patch` is the complete upstream-base-to-branch-tip diff, retained
as a recovery asset; CI fetches the branch tip directly and does not apply that
Logos diff again. To reconstruct from clean upstream source, apply the Logos diff
first, then the Piper patch, then the SAPI enumeration and PCM write compatibility patches. The release source
archive already contains all changes. The enumeration patch implements registry
value-name enumeration used by .NET System.Speech; it is not proof that the
Logos speech failure has been resolved.

## Included Logos branch commits

```text
759cf433244d35f334330119e24c6b68a2b6ac17 ntdll: Don't write zeros into untouched page protection chunks.
b900ee17546f7ac4b5b1d8fb286318a1fb8fcf88 server, ntdll: Share page-aligned copies of misaligned read-only image sections.
548a6d466cda5b29502acf3bda90c7bcaccdad2f dwrite/tests: Test custom collections containing unsupported files.
c34bd1344ceb781d27cf301815c5b61002b0f1e9 dwrite: Skip unsupported files when creating custom collections.
88957547ab8c9e9c453f4f9fae3f9e27d2788566 d3d9: Wait for GetRenderTargetData() to complete.
bd041ce576b0661cf5499297daf302a76f7c85da wined3d: Use the texture size for blits to swapchain textures through an FBO.
0f230e2df5ea489e1ce0889c76e9bceb84d0fd0d evr/mixer: Request input whenever ProcessOutput() needs more input.
ed6e1585219d849a31172cf3c0c2391f9faf0ebf evr/mixer: Send sample requests after releasing the mixer lock.
afb85067a7de9ba5f0efb2779ccb0a71a80a645e mf/evr: Handle sample requests from the mixer without the renderer lock.
83a8581a63e3272b5a4c633d0bf54f2359769d72 prntvpt: Return the driver's full DEVMODE from PTConvertPrintTicketToDevMode.
43f7cb6e075593b388dbf18d9c77b2b9632faced prntvpt/tests: Test that PTConvertPrintTicketToDevMode returns the driver's private data.
daa1f48b120d09fc594602372dbaf74ea94e7d3e wineps: Name glyphs after their character when the font has no glyph names.
e1ab975996fc764848a97a92629c1dcfabcf20e6 xpsprint: Don't export StartXpsPrintJob stubs.
60130c04ef83f62d7134ae872c01713204c7ce20 wineps: Map ligatures and alternate glyphs back to their text through GSUB.
9a962f8799c79149af0be85d8d8f7b92951c1cc5 wineps: Mark ligature glyphs with their text through ActualText spans.
f9641663888598dbb69265e1ede182deeb9b27bd Revert "wined3d: Update the context DC from its swapchain if it changed."
3b19eb0e45ac5f57301073fc9e721cac7829dc93 Revert "wined3d: Create / release the window DCs with the swapchains."
```

The CI audio tests do not launch Logos or validate these changes inside Logos.
Native .NET, Logos, Piper and voice models are not included. Normal AppRun program
launches preserve the user's Wine DLL overrides, including native mscoree.

The PCM write patch initializes the accepted-byte count to the requested size
before each site callback. System.Speech's EngineSiteSapi.Write does not store
through that pointer. Partial writes, explicit zero progress, failed writes and
cancellation remain checked; CI exercises the missing-count case with full PCM
comparison. The helper also sets HKCU DefaultTokenId for .NET alongside Wine's
HKLM DefaultDefaultTokenId when --make-default is requested.

## Regression-revert update

The update from `9a962f8799c79149af0be85d8d8f7b92951c1cc5` to
`3b19eb0e45ac5f57301073fc9e721cac7829dc93` includes both new revert commits:
`f9641663888598dbb69265e1ede182deeb9b27bd` and the new tip. They revert
`92f5d5bc7c8412924e7cb4f6f715ecc9c4e4dd13` and
`6048ac5dfebd7090672ec1c26e6e15dfd51d5a8d`, respectively. The exact reverted
commit IDs are also recoverable from the pinned branch history.

Only `dlls/wined3d/context_gl.c`, `dlls/wined3d/swapchain.c` and
`dlls/wined3d/wined3d_private.h` change. CI permits this exact ancestor transition
with the same toolchain, patch and configure hashes, verifies the two-commit count
and changed-file allowlist, then rebuilds affected dependencies. All original
integration and failure tests, enumeration checks, AppImage dispatch and real
packaged-Piper synthesis remain enabled. The reverted desktop regression itself
still requires testing in Logos; speech tests do not establish graphics behavior.
