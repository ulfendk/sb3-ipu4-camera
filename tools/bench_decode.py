"""Time the webcamd decode pipeline on the raw frames left in /dev/shm.

Usage: PYTHONPATH=<lib dir> python3 bench_decode.py <surface_webcamd.py>
"""
import importlib.util
import sys
import time

import numpy as np

import surface_cam as sc

spec = importlib.util.spec_from_file_location("wd", sys.argv[1])
wd = importlib.util.module_from_spec(spec)
sys.argv = sys.argv[:1]
spec.loader.exec_module(wd)

for name, w, h, stride in (("front-standard", 1296, 972, 1664), ("front-hq", 2592, 1944, 3264)):
    try:
        raw = open(f"/dev/shm/surface-raw-{name}.0", "rb").read()
    except OSError:
        continue
    cam = sc.CAMS["front"]
    t = time.perf_counter()
    for _ in range(5):
        sc.unpack_mipi10_u16(raw[: stride * h], w, h, stride, line_off=4)
    tu = (time.perf_counter() - t) / 5
    tone = wd.LockedTone("front")
    cfg = wd.PROFILES[name]
    ts = []
    bgr = None
    for _ in range(10):
        t = time.perf_counter()
        bgr = wd.decode(cam, raw, w, h, stride, tone, cfg["crop_r"], cfg["crop_b"], cfg.get("crop_l", 0))
        ts.append(time.perf_counter() - t)
    med = float(np.median(ts[3:]))
    print(f"{name}: unpack {tu * 1000:.0f} ms, decode {med * 1000:.0f} ms -> {1 / med:.1f} fps max, "
          f"out {None if bgr is None else bgr.shape}")
