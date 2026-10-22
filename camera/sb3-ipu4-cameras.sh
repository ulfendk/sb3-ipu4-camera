#!/bin/bash
# Surface Book 3: bring up the IPU4P camera stack after boot.
# Order matters: core -> psys (does CSE auth) -> isys -> sensors.
# Never rmmod these modules; reloading isys alone oopses.
set -uo pipefail

log() { echo "sb3-ipu4: $*"; }

if [[ $(uname -r) != *surface-ipu4* ]]; then
  log "not a surface-ipu4 kernel, skipping"
  exit 0
fi

for n in 00 01 02; do
  dev=/sys/bus/platform/devices/INT3472:$n
  if [[ -e $dev && ! -e $dev/driver ]]; then
    echo "INT3472:$n" > /sys/bus/platform/drivers/int3472-discrete/bind 2>/dev/null \
      && log "bound INT3472:$n"
  fi
done

timeout -k 5 45 modprobe intel_ipu4p || log "intel_ipu4p modprobe failed"

for _ in $(seq 1 40); do
  [[ -e /dev/mei0 ]] && break
  sleep 0.25
done

timeout -k 5 90 modprobe intel_ipu4p_psys || log "psys modprobe failed"
timeout -k 5 60 modprobe intel_ipu4p_isys || log "isys modprobe failed"

for _ in $(seq 1 50); do
  if journalctl -k -b --no-pager | grep -q 'CSE authenticate_run done'; then
    log "CSE authenticated"
    break
  fi
  if journalctl -k -b --no-pager | grep -q 'CSE boot_load failed'; then
    log "CSE boot_load failed"
    break
  fi
  sleep 0.4
done

timeout -k 2 12 modprobe ov5693 || log "ov5693 modprobe failed"
timeout -k 2 8 modprobe ov8865 || log "ov8865 modprobe failed"
timeout -k 2 5 modprobe dw9719 || true

# Sensors may have probed before the ISYS existed; rebind any left unbound.
for pair in "ov5693 i2c-INT33BE:00" "ov8865 i2c-INT347A:00" "dw9719 i2c-INT347A:00-VCM"; do
  read -r drv dev <<<"$pair"
  if [[ -e /sys/bus/i2c/devices/$dev && ! -e /sys/bus/i2c/devices/$dev/driver ]]; then
    echo "$dev" > "/sys/bus/i2c/drivers/$drv/bind" 2>/dev/null && log "bound $dev to $drv"
  fi
done

log "done"
