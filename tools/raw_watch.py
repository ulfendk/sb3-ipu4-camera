"""Sample the Front-HQ shm buffers while streaming; report lines with real payload."""
import sys
import time

import numpy as np

STRIDE, H, PAYLOAD = 3264, 1944, 2592 * 10 // 8
dur = float(sys.argv[1])
out = sys.argv[2] if len(sys.argv) > 2 else None
end = time.monotonic() + dur
hist = []
best = (0, None)
while time.monotonic() < end:
    for f in ("/dev/shm/surface-raw-front-hq.0", "/dev/shm/surface-raw-front-hq.1"):
        try:
            b = np.fromfile(f, np.uint8)
        except OSError:
            continue
        if b.size < STRIDE * H:
            continue
        rows = b[: STRIDE * H].reshape(H, STRIDE)
        hdr_ok = rows[:, 0] != 0  # line written by the IPU
        pay = rows[:, 4 : 4 + PAYLOAD : 16]
        idx = np.flatnonzero(hdr_ok & ((pay != 0xFF).mean(1) > 0.05))
        hist.append(len(idx))
        if len(idx) > best[0]:
            best = (len(idx), (int(idx[0]), int(idx[-1]), round(float(pay[idx].mean()), 1)))
            if out:
                b.tofile(out)
    time.sleep(0.1)
h = np.array(hist) if hist else np.zeros(1)
print(f"  samples={len(hist)} frames_with_data={int((h > 0).sum())} "
      f"median_lines={int(np.median(h))} best={best[0]}/{H} first/last/mean={best[1]}")
