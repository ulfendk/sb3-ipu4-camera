# Front camera (OV5693) bring-up on IPU4P

The front sensor sits on CSI-2 receiver 2 (firmware source 7), two data
lanes at 419.2 MHz. Three independent faults kept it at zero usable frames;
all three fixes are needed.

## 1. PHY building block 10 never configured — patch 206

`ipu4p_isys_bb_cfg()` only programmed the D-PHY building blocks from Intel's
reference board (4, 6, 12, 14). The rear sensor's block (6) is in that list;
the front sensor's block (10) is not, so its analogue front end stayed off.

Symptom: receiver enabled, `hs=0x0 lp=0x0` — not even LP-11 on the lanes.
Fix (values from ruslanbay/ipu4-drivers ConsultingFuture4200 0049, verified
on Surface Pro 7): add `{10, 13, 32, 0x15}`. Do not add block 8 the same
way; it injects sync errors on 10.

## 2. Receiver delay registers are 4 bytes off — patch 208

The IPU4 header names `0x2c/0x30` as clock-lane termen/settle and
`0x34+8n/0x38+8n` as data-lane termen/settle. The Windows driver (traced on
SP7 by georgemihaila/sp7-ipu4-camera) writes:

```
0x30 <- 0      0x34 <- 1155       (clock)
0x38+8i <- 0   0x3c+8i <- 1269    (data lane i)
```

i.e. on IPU4P the termen/settle pairs start 4 bytes later. Every "settle"
value the driver wrote landed in a termination register and the real settle
registers stayed 0. `sb3_front_win_timing=1` programs the Windows layout for
the active lanes only (the 8-lane version walks into other registers and
kills ISYS). 1000/1100 and 1300/1450 lock as well, so it is not marginal.

## 3. Non-continuous MIPI clock — module option

`ov5693 mipi_ctrl00=0x2d` (what Windows writes) gates the clock lane between
lines. With fixes 1 and 2 in place the receiver still lost sync a few lines
into each frame (`DPHY non-recoverable sync`, `Frame sync error`). The
sensor's power-on default (`0`, continuous clock) locks every frame.

## Result

`sb3-ipu4-front.conf`:

```
options intel_ipu4p_isys sb3_front_timing_quirk=0 sb3_front_win_timing=1 sb3_front_clk_ticks=1155 sb3_front_data_ticks=1269
options ov5693 mipi_ctrl00=0
```

Front-HQ: 192/192 sampled frames complete (1944/1944 lines), no receiver
errors apart from one clock-lane ULPS exit at stream start.

## Ruled out along the way

- Settle values through the old defines (684/661, 684/880, 1392/1392, 0/1100):
  they never reached the settle registers.
- `NOF_ENABLED_LANES` = lanes − 1: raw lane count is correct; −1 floods
  errors and kills ISYS.
- Binning: the binned 1296×972 mode locks fine once the above is fixed
  (`ov5693 no_binning`, patch 207, stays off).
- The line header byte (`0x5…` front vs `0x3…` rear) is the receiver index
  + 3, not an error flag.

## Diagnostics

- `intel_ipu4p_isys sb3_front_err_irq=1` (patch 209) unmasks port-2 error
  IRQs so `csi 2 error snapshot … err=` shows real bits (masked by default:
  without it every snapshot reads `err=0x0`).
- With the sensor test pattern (`v4l2-ctl -d <ov5693 subdev> -c test_pattern=2`)
  constant `0x3FF` lines are IPU filler, not sensor output.

## Image pipeline

`camera/front_isp.py` replaces the generic decode for the front camera:
per-CFA-site lookup table (black level 16, white-balance gain, clip, sRGB
gamma) on the mosaic, 8-bit demosaic, saturation, orientation. ~11 ms per
1296×972 frame. Auto-exposure and grey-world white balance run on linear
mosaic statistics; exposure first, then analogue gain (code 16 = 1×).
