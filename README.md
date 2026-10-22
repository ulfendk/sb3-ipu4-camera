# sb3-ipu4-camera

Working front and rear cameras on the **Surface Book 3** (Intel IPU4P,
OV5693 front / OV8865 rear) under Arch Linux, exposed to apps such as Teams,
Firefox and Chromium as ordinary webcams.

Two pacman packages:

| Package | Directory | What it is |
|---|---|---|
| `linux-surface-ipu4` | [`kernel/`](kernel) | linux-surface kernel + the IPU4/IPU4P driver series + SB3 fixes |
| `sb3-ipu4-cameras` | [`camera/`](camera) | IPU bring-up service, webcam daemon (RAW10 → v4l2loopback), udev rules, module options |

The IR sensor (OV7251) is not supported.

## Install

```sh
# Kernel (long build; needs ~25 GB free)
cd kernel && ./update-kernel.sh          # builds for the installed linux-surface version
sudo pacman -U kernel/linux-surface-ipu4-*.pkg.tar.zst

# Webcam stack
cd camera && makepkg -si
sudo systemctl enable --now sb3-ipu4-cameras.service surface-webcam.service
```

Make the IPU4 kernel the default boot entry (Limine, as on Omarchy):

```sh
sudo sed -i 's|^default_entry: .*|default_entry: Omarchy/linux-surface-ipu4|' /boot/limine.conf
```

Then reboot into `linux-surface-ipu4`. Apps see these cameras:

| Device | Name | Mode |
|---|---|---|
| `/dev/video60` | Surface-Front-Standard | 1296×972, 30 fps (**use this for calls**) |
| `/dev/video61` | Surface-Front-HQ | 1920×1440 from full-res sensor, max 15 fps |
| `/dev/video62` | Surface-Front-Fast | 16:9 crop of Standard |
| `/dev/video63`–`65` | Surface-Back-* | rear camera equivalents |

The daemon only powers a sensor while an app has its device open.

## Kernel upgrades

`linux-surface-ipu4` is built locally, so pacman never upgrades it. When
`linux-surface` updates, a pacman hook from `sb3-ipu4-cameras` prints a
reminder. Then:

```sh
kernel/update-kernel.sh            # follow the installed linux-surface version
kernel/update-kernel.sh 7.2.12.arch1 --check   # or: a specific version, patches only
```

Minor releases (7.2.x) normally apply as-is. For a new major version, refresh
`0001`–`0015` from `linux-surface/patches/<ver>/` (keeping the local changes
in `0013-cameras.patch`) and rebase the `1xx` IPU4 series; `--check` stops at
the first patch that fails.

## Tuning

`/etc/default/surface-webcam` (read by `surface-webcam.service`):

```sh
SURFACE_WEBCAM_WARMTH=0.10   # front white-balance tilt: 0 neutral, ~0.15 warm
```

## Patches

| Range | Source |
|---|---|
| `0001`–`0015` | [linux-surface](https://github.com/linux-surface/linux-surface) `patches/7.2`, `0013`–`0015` adjusted |
| `100`–`155` | IPU4 driver series from [ruslanbay/ipu4-drivers](https://github.com/ruslanbay/ipu4-drivers), adapted to 7.2 |
| `200`–`205` | SB3 driver fixes (queue/vb2 lifetime, buttress clock, uapi) |
| `206`–`209` | SB3 front camera — see [docs/front-camera.md](docs/front-camera.md) |

Firmware `kernel/ipu4-20191030.bin` is Intel's IPU4P CPD image, redistributed
under [`LICENSE.ipu4-firmware`](kernel/LICENSE.ipu4-firmware).

## Debug tools

[`tools/`](tools): `front_sweep.sh` streams Front-HQ under a list of receiver
settings and reports complete lines per frame; `bench_*.py` time the image
pipeline on frames left in `/dev/shm`.

## Credits and licences

- `kernel/` patches modify GPL-2.0 Linux sources and are GPL-2.0-only
  ([LICENSE](LICENSE)). Sources: linux-surface, ruslanbay/ipu4-drivers
  (IPU4 series, itself derived from Intel's GPL-2.0 driver), and the SB3
  DPHY work in linux-surface PR #2289.
- `camera/` (webcam daemon, `surface_cam.py`, `ipu_guard.py`, `pycompat.py`,
  `raw_hold.c`, service and udev files) is based on the
  `contrib/sb3-ipu4-cameras` overlay by **popos123** in
  [linux-surface PR #2289](https://github.com/linux-surface/linux-surface/pull/2289),
  which carries **no explicit licence**; it is included here with credit,
  and will be removed or relicensed at the author's request. `front_isp.py`,
  the IR-sensor wait fix and the kernel-check hook are new here.
- `kernel/ipu4-20191030.bin`: Intel IPU4P firmware (from the Windows
  "Intel - Camera - 42.18362.3.16827" driver, as published by
  ruslanbay/ipu4-drivers), under
  [`LICENSE.ipu4-firmware`](kernel/LICENSE.ipu4-firmware).
