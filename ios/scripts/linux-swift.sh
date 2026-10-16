#!/usr/bin/env bash
#
# A Swift toolchain on Linux, for compiling and checking the platform-neutral part of the iOS player
# (PanimCore, PanimAudio's Ogg demuxer, PanimVerify) where there is no Mac.
#
# swift.org is not reachable from the development environment, but Ubuntu's archive is, and Ubuntu 25.04
# packages Swift 5.10. The debs are unpacked into a cache, not installed.
#
#   source ios/scripts/linux-swift.sh      # puts swift on PATH (fetches ~400 MB the first time)
#   cd ios && swift build && swift test
CACHE="${PANIM_SWIFT_CACHE:-$HOME/.cache/pocketanim-swift}"
ROOT="$CACHE/root"
if [ ! -x "$ROOT/usr/libexec/swift/bin/swift" ]; then
    mkdir -p "$CACHE/debs" "$ROOT"
    archive=http://archive.ubuntu.com/ubuntu
    for list in universe main; do
        curl -fsS "$archive/dists/plucky/$list/binary-amd64/Packages.gz" | zcat \
            | awk '/^Package: (swiftlang|libswiftlang|libicu76|libpython3.13|libpython3.13-minimal|libpython3.13-stdlib)$/{p=1} p&&/^Filename:/{print $2; p=0}'
    done | while read -r f; do
        curl -fsS -o "$CACHE/debs/$(basename "$f")" "$archive/$f"
    done
    for d in "$CACHE"/debs/*.deb; do dpkg-deb -x "$d" "$ROOT"; done
fi
export PATH="$ROOT/usr/libexec/swift/bin:$PATH"
export LD_LIBRARY_PATH="$ROOT/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
