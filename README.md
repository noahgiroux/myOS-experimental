# Current Personal

Personal Current BlueBuild images for niche hardware, derived from Current’s
published Fedora GNOME image. The normal Current image is deliberately
unchanged. This repository publishes independent hardware images:

- `ghcr.io/noahgiroux/fedora-gnome-wl:latest` — the Broadcom `wl` image,
  using only `broadcom-wl.yml`.
- `ghcr.io/noahgiroux/fedora-gnome-ux8406:latest` — a UX8406-specific layer
  on `ghcr.io/pelagians/fedora-gnome:latest`. It does not inherit or share
  hardware-specific code with the WL image.

## UX8406 image

The UX8406 layer adds only `gnome-monitor-config`, `iio-sensor-proxy`,
`inotify-tools`, and `libwacom-utils`. It recognizes the UX8406MA profile:

- DMI: `ASUSTeK COMPUTER INC.` / `UX8406MA`
- detachable keyboard: `0b05:1b2c`
- upper touchscreen/tablet: `04f3:425b`
- lower touchscreen/tablet: `04f3:425a`
- preferred connectors: `eDP-1` and `eDP-2`
- preferred mode: `2880x1800@120`
- panel baseline: `SDC`, `0x419d`, `0x00000000`

After login, the user service verifies GNOME Wayland, discovers Mutter’s
connected monitors and exact mode IDs, maps both touch and tablet devices,
selects the attached/detached layout, and watches udev keyboard events and
`monitor-sensor` rotation changes. Automatic changes stop when an external
monitor is present. Use the helper for inspection or manual control:

```bash
/usr/libexec/current-zenbook-duo check-hardware
/usr/libexec/current-zenbook-duo status
/usr/libexec/current-zenbook-duo top
/usr/libexec/current-zenbook-duo bottom
/usr/libexec/current-zenbook-duo both
/usr/libexec/current-zenbook-duo toggle
/usr/libexec/current-zenbook-duo setup-inputs
```

Display and battery defaults are in `/etc/current/zenbook-duo.conf`:

```ini
[Display]
TopConnector=
BottomConnector=
Mode=
Scale=auto

[Battery]
ChargeLimit=80
```

The root services synchronize the lower OLED by normalized brightness ratio
and apply the charge threshold only when the kernel exposes the standard
`BAT0/charge_control_end_threshold` interface. The GNOME service has no sudo
or privileged command path.

## Installation

For an existing bootc installation:

```bash
sudo bootc switch ghcr.io/noahgiroux/fedora-gnome-ux8406:latest
sudo systemctl reboot
```

These hardware images are experimental. Before promoting the UX8406 image
beyond testing, verify display connector/mode/scale discovery,
external-monitor protection, USB and Bluetooth
keyboard attach/detach, touch/pen mapping, rotation axes, both backlight names,
suspend/resume synchronization, battery threshold support, speakers,
microphones and headset output, IPU6 webcam, and Intel `ivpu` NPU behavior.

Intentionally deferred pending physical UX8406 testing: keyboard-backlight USB
detachment, lower-touch inhibition, Intel PSR or other kernel arguments, DKMS
or custom kernels, patched Mutter/libwacom, and out-of-tree audio/camera/NPU
workarounds. In particular, the Fedora kernel’s `1043:1c43` quirk must be
tested on the built image for the analog headset microphone before any audio
workaround is considered.

Run local checks with `./scripts/validate-ux8406.sh`.
