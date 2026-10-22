#!/bin/bash
# Usage: front_sweep.sh "quirk:clk:data[:win:lane]" ...
# For each setting: write the SB3 front receiver params, open Front-HQ
# (/dev/video61) so webcamd streams it, and sample the raw shm buffers for
# lines carrying real payload (IPU-written header, not 0xFF filler).
P=/sys/module/intel_ipu4p_isys/parameters
HERE=$(dirname "$(readlink -f "$0")")
OUT=${OUT:-/tmp/claude-1000/front-sweep}
mkdir -p "$OUT"

wait_idle() {
  for _ in $(seq 1 30); do
    journalctl -u surface-webcam -o cat -n 1 --no-pager | grep -q 'cam=idle' && return 0
    sleep 1
  done
  echo "  (daemon not idle after 30 s)"
}

for spec in "$@"; do
  IFS=: read -r quirk clk data win lane <<<"$spec"
  win=${win:-N} lane=${lane:--1}
  wait_idle
  echo "$quirk" > $P/sb3_front_timing_quirk
  echo "$clk" > $P/sb3_front_clk_ticks
  echo "$data" > $P/sb3_front_data_ticks
  echo "$win" > $P/sb3_front_win_timing
  echo "$lane" > $P/sb3_front_lane_reg
  [[ -w $P/sb3_front_err_irq ]] && echo "${ERR_IRQ:-Y}" > $P/sb3_front_err_irq
  since=$(date +%s)
  echo "=== quirk=$quirk clk=$clk data=$data win=$win lane_reg=$lane mipi_ctrl00=$(cat /sys/module/ov5693/parameters/mipi_ctrl00)"
  timeout -k 2 14 ffmpeg -hide_banner -loglevel quiet -f v4l2 -i /dev/video61 -f null - >/dev/null 2>&1 &
  sleep 3
  python3 -I "$HERE/raw_watch.py" 10 "$OUT/best-$quirk-$clk-$data-$win-$lane.raw"
  wait 2>/dev/null
  journalctl -k --since "@$since" -o cat --no-pager \
    | grep -E 'Windows timing|settle applied|set_stream enable done|csi2-2 error|receiver_errors=0x[1-9a-f]|err=0x[1-9a-f]|power cycle|close error' \
    | sed -E 's/^intel-ipu6 intel-ipu60: //' | sort | uniq -c | head -5
  journalctl -u surface-webcam --since "@$since" -o cat --no-pager | grep -E 'failed|dead' | head -2
done
