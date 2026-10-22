"""Time front_isp.process on the raw frames in /dev/shm and save previews.

Usage: PYTHONPATH=<lib dir>:<pkg dir> python3 bench_front_isp.py <out dir>
"""
import sys
import time

import cv2
import numpy as np

import front_isp
import surface_cam as sc

out = sys.argv[1]
for name, w, h, stride, out_wh in (
    ("front-standard", 1296, 972, 1664, None),
    ("front-hq", 2592, 1944, 3264, (1920, 1440)),
):
    try:
        raw = open(f"/dev/shm/surface-raw-{name}.0", "rb").read()
    except OSError:
        continue
    cam = sc.CAMS["front"]
    for _ in range(40):  # let AWB settle
        front_isp.process(cam, raw, w, h, stride, out_wh)
    ts = []
    for _ in range(15):
        t = time.perf_counter()
        bgr = front_isp.process(cam, raw, w, h, stride, out_wh)
        ts.append(time.perf_counter() - t)
    med = float(np.median(ts))
    st = front_isp.STATE
    print(f"{name}: {med * 1000:.1f} ms -> {1 / med:.0f} fps max, out {bgr.shape}, "
          f"wb={np.round(st.wb, 2)} luma={st.luma:.3f} clipped={st.clipped:.3f} "
          f"ae={front_isp.ae_step(1030)}")
    front_isp.STATE.ae_t = 0
    cv2.imwrite(f"{out}/isp-{name}.jpg", bgr)
