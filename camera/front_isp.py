"""Front camera (OV5693) software ISP: RAW10 -> display BGR, plus AE/AWB.

The generic decode() path in webcamd stacks per-frame heuristics (stretch,
LockedTone, magenta/green fixes) that cost ~30 ms per 1.3 MP frame and keep
the image dark when a lamp is in view. This is a plain pipeline that does
the per-pixel work once, on the single-channel mosaic:

  unpack -> per-CFA-site LUT (black level, WB gain, clip, gamma) ->
  8-bit demosaic -> saturation -> orient/resize

Clipping each site at white before gamma makes a blown lamp saturate to
white instead of pink. AE and AWB statistics come from a linear mosaic
subsample, so they do not depend on the tone curve. State persists between
streams so a new session starts from the last exposure and white balance.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

import surface_cam as sc

BLACK_LEVEL = 16  # 10-bit; OV5693 optical-black rows read exactly 16
WHITE = 1023 - BLACK_LEVEL

# AE: centre-weighted mean linear luma as a fraction of white.
# 0.16 linear ≈ 110/255 after the gamma curve below.
AE_TARGET = 0.16
AE_DEADBAND = 0.12  # relative error tolerated before stepping
AE_INTERVAL = 0.15  # s between steps; the sensor applies values ~2 frames later
AE_CLIP_MAX = 0.04  # max clipped fraction in the centre region

GAIN_MIN, GAIN_MAX = 16, 127  # analogue gain code, 16 = 1x (libcamera helper)

SATURATION = 1.25
WB_ALPHA = 0.08  # EMA weight per frame; ~1 s to settle at 15-30 fps
WB_LIMITS = (0.6, 3.0)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


# Grey world makes the scene average exactly neutral, which reads as cold.
# Warmth tilts the display gains: R x (1 + w), B x (1 - w). 0 = neutral.
WARMTH = _env_float("SURFACE_WEBCAM_WARMTH", 0.06)
_WARM = np.array([1.0 - WARMTH, 1.0, 1.0 + WARMTH])  # B, G, R

# Mosaic sites for OpenCV's COLOR_BayerRG2BGR: (row, col) -> B/G/R index.
_SITES = (((0, 0), 0), ((0, 1), 1), ((1, 0), 1), ((1, 1), 2))
_LUMA_W = np.array([0.114, 0.587, 0.299], np.float32)  # B, G, R


@dataclass
class FrontState:
    wb: np.ndarray = field(default_factory=lambda: np.array([1.9, 1.0, 1.25]))  # B, G, R
    exposure: int = 900
    gain: int = 32
    ae_t: float = 0.0
    luma: float = 0.0
    clipped: float = 0.0
    luts: dict = field(default_factory=dict)
    lut_wb: np.ndarray | None = None


STATE = FrontState()


def _gamma(x: np.ndarray) -> np.ndarray:
    """Linear 0..1 -> sRGB-encoded 0..255."""
    y = np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)
    return np.clip(np.round(y * 255.0), 0, 255).astype(np.uint8)


def _site_luts() -> list[np.ndarray]:
    """One 10-bit -> 8-bit table per colour: black level, WB gain, clip, gamma.

    Rebuilt only when the WB gains have moved by more than ~0.5%.
    """
    wb = STATE.wb * _WARM
    wb = wb / wb.min()
    if STATE.lut_wb is None or np.max(np.abs(wb / STATE.lut_wb - 1)) > 0.005:
        v = np.clip(np.arange(1024, dtype=np.float64) - BLACK_LEVEL, 0, None) / WHITE
        STATE.luts = {c: _gamma(np.minimum(v * wb[c], 1.0)) for c in range(3)}
        STATE.lut_wb = wb
    return [STATE.luts[c] for c in range(3)]


def _stats(bayer: np.ndarray) -> None:
    """Update AWB and AE measurements from a linear mosaic subsample."""
    h, w = bayer.shape
    step = max(2, (w // 160) & ~1)  # even, so every sample keeps its site
    sub = {}
    for (y, x), c in _SITES:
        plane = bayer[y::step, x::step].astype(np.float32)
        plane = np.clip(plane - BLACK_LEVEL, 0, None) / WHITE
        sub.setdefault(c, []).append(plane)
    hh = min(p.shape[0] for ps in sub.values() for p in ps)
    ww = min(p.shape[1] for ps in sub.values() for p in ps)
    b = sub[0][0][:hh, :ww]
    g = (sub[1][0][:hh, :ww] + sub[1][1][:hh, :ww]) * 0.5
    r = sub[2][0][:hh, :ww]
    luma = 0.114 * b + 0.587 * g + 0.299 * r
    clipped = np.maximum(np.maximum(b, g), r) >= 0.98

    # AWB: grey world on mid-tones, ignoring clipped and very dark pixels.
    m = (luma > 0.03) & (luma < 0.7) & ~clipped
    if m.sum() > 200:
        means = np.array([b[m].mean(), g[m].mean(), r[m].mean()])
        if np.all(means > 1e-4):
            target = np.clip(means[1] / means, *WB_LIMITS)
            STATE.wb = (1 - WB_ALPHA) * STATE.wb + WB_ALPHA * target

    # AE: centre third weighted 3:1 against the whole frame.
    cy, cx = slice(hh // 3, hh - hh // 3), slice(ww // 3, ww - ww // 3)
    STATE.luma = (float(luma.mean()) + 3 * float(luma[cy, cx].mean())) / 4
    STATE.clipped = float(clipped[cy, cx].mean())


def ae_step(exp_max: int) -> tuple[int, int] | None:
    """Return a new (exposure, gain) when the image needs adjusting, else None."""
    now = time.monotonic()
    if now - STATE.ae_t < AE_INTERVAL:
        return None
    STATE.ae_t = now
    err = AE_TARGET / max(STATE.luma, 1e-4)
    if STATE.clipped > AE_CLIP_MAX:
        err = min(err, 0.85)
    elif abs(err - 1.0) < AE_DEADBAND:
        return None
    # Move part of the way (log-space damping), at most 2x per step.
    ratio = float(np.clip(err**0.6, 0.5, 2.0))
    total = STATE.exposure * STATE.gain * ratio
    # Exposure first (no noise cost), then analogue gain.
    exposure = int(np.clip(total / GAIN_MIN, 4, exp_max))
    gain = int(np.clip(round(total / exposure), GAIN_MIN, GAIN_MAX))
    if exposure == STATE.exposure and gain == STATE.gain:
        return None
    STATE.exposure, STATE.gain = exposure, gain
    return exposure, gain


def _saturation_matrix() -> np.ndarray:
    k = SATURATION - 1.0
    return (np.eye(3, dtype=np.float32) * (1 + k) - k * np.tile(_LUMA_W, (3, 1))).astype(np.float32)


_SAT = _saturation_matrix()


def process(
    cam: sc.Cam,
    raw: bytes,
    w: int,
    h: int,
    stride: int,
    out_wh: tuple[int, int] | None = None,
    line_off: int = 4,
) -> np.ndarray:
    """RAW10 frame -> oriented uint8 BGR, optionally resized to out_wh."""
    bayer = sc.unpack_mipi10_u16(raw[: stride * h], w, h, stride, line_off=line_off)
    _stats(bayer)

    luts = _site_luts()
    mosaic = np.empty((h, w), np.uint8)
    for (y, x), c in _SITES:
        mosaic[y::2, x::2] = luts[c][bayer[y::2, x::2]]

    binned = w < 2000
    bgr = cv2.cvtColor(mosaic, cv2.COLOR_BayerRG2BGR_EA if binned else cv2.COLOR_BayerRG2BGR)
    if out_wh is not None and out_wh[0] < bgr.shape[1]:
        bgr = cv2.resize(bgr, out_wh, interpolation=cv2.INTER_AREA)
    bgr = cv2.transform(bgr, _SAT)
    bgr = sc._orient(bgr, cam)
    if out_wh is not None and (bgr.shape[1], bgr.shape[0]) != out_wh:
        bgr = cv2.resize(bgr, out_wh, interpolation=cv2.INTER_LINEAR)
    return bgr
