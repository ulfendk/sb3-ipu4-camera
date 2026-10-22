#!/bin/bash
# pacman hook: warn when linux-surface moves ahead of linux-surface-ipu4.
# The IPU4 kernel is built locally, so pacman never upgrades it on its own.
ver() { pacman -Q "$1" 2>/dev/null | awk '{print $2}' | sed 's/-[0-9]*$//'; }
stock=$(ver linux-surface)
ipu4=$(ver linux-surface-ipu4)
[[ -n $stock && -n $ipu4 ]] || exit 0
if [[ $(vercmp "$stock" "$ipu4") -gt 0 ]]; then
  echo ">> linux-surface is now $stock but linux-surface-ipu4 (default boot, cameras) is $ipu4."
  echo ">> Rebuild it from the sb3-ipu4-camera repo: kernel/update-kernel.sh"
fi
