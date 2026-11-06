# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
# Increment this revision to refresh signed distribution packages in the cache.
# Build dependencies only: no accounts, tokens, Piper, models, or Wine binaries.
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential bison flex pkg-config gcc-mingw-w64-x86-64 \
    g++-mingw-w64-x86-64 libasound2-dev libpulse-dev libdbus-1-dev \
    libfontconfig1-dev libfreetype-dev libgnutls28-dev libunwind-dev \
    libx11-dev libxcomposite-dev libxcursor-dev libxext-dev libxi-dev \
    libxinerama-dev libxrandr-dev libxrender-dev libxfixes-dev \
    libgl-dev libosmesa6-dev libvulkan-dev libudev-dev \
    libusb-1.0-0-dev libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
    libpng-dev libjpeg-dev libtiff-dev libxml2-dev libxslt1-dev \
    libpcap-dev liblcms2-dev libzstd-dev zlib1g-dev \
    squashfs-tools xz-utils curl git python3 xvfb xauth ca-certificates \
    && rm -rf /var/lib/apt/lists/*
