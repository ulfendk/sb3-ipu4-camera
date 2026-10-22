#!/bin/bash
# Retarget linux-surface-ipu4 at a new kernel and build it.
#
# Usage: kernel/update-kernel.sh [VERSION] [--check]
#   VERSION  Arch kernel version, e.g. 7.2.12.arch1. Defaults to the
#            installed linux-surface package, so the IPU4 kernel follows it.
#   --check  Stop after applying the patches (no build).
#
# Minor releases (7.2.x) normally apply cleanly. A new major version
# (e.g. 7.3) needs the linux-surface patches 0001-0015 refreshed from
# linux-surface/patches/<ver>/ and may need the IPU4 series rebased;
# prepare() then stops at the first patch that does not apply.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

check=0
version=
for arg in "$@"; do
  case $arg in
    --check) check=1 ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) version=$arg ;;
  esac
done

if [[ -z $version ]]; then
  version=$(pacman -Q linux-surface 2>/dev/null | awk '{print $2}')
  version=${version%-*}
  [[ -n $version ]] || { echo "linux-surface not installed; pass VERSION" >&2; exit 1; }
fi
[[ $version =~ ^[0-9]+\.[0-9]+(\.[0-9]+)?\.arch[0-9]+$ ]] || {
  echo "bad version '$version' (want e.g. 7.2.12.arch1)" >&2; exit 1; }

current=$(sed -n 's/^pkgver=//p' PKGBUILD)
if [[ $version != "$current" ]]; then
  echo ">> $current -> $version"
  sed -i "s/^pkgver=.*/pkgver=$version/; s/^pkgrel=.*/pkgrel=1/" PKGBUILD
  rm -rf src
fi

echo ">> updating checksums (downloads the kernel tarball)"
updpkgsums

echo ">> extracting and applying patches"
makepkg --nobuild --cleanbuild --force --skippgpcheck --noconfirm > prepare.log 2>&1 || {
  echo "!! prepare failed; last lines of kernel/prepare.log:" >&2
  grep -nE 'Applying patch|FAILED|rejects|malformed|ERROR' prepare.log | tail -8 >&2
  exit 1
}
echo ">> all patches applied"
(( check )) && exit 0

echo ">> building (takes a while)"
MAKEFLAGS="-j$(nproc)" makepkg --noextract --force --skippgpcheck --noconfirm
echo ">> done; install with:"
echo "   sudo pacman -U $(ls -t "$PWD"/linux-surface-ipu4-[0-9]*.pkg.tar.zst | head -1)"
