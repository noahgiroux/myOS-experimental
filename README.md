# Current Personal

Personal Current images for niche hardware. Both images inherit the normal
Current Fedora GNOME base, `ghcr.io/pelagians/fedora-gnome:latest`, and retain
their own narrow hardware layer:

- `ghcr.io/noahgiroux/fedora-gnome-wl:latest` — Broadcom `wl` only.
- `ghcr.io/noahgiroux/fedora-gnome-ux8406:latest` — ASUS Zenbook Duo UX8406
  support only. It neither imports nor changes the WL layer.

## UX8406

The supported profile is the 2024 UX8406MA. Detection requires
`ASUSTeK COMPUTER INC.` and prefers DMI `board_name=UX8406MA`; a longer
`product_name` containing `UX8406MA` is accepted as a fallback. UX8406CA is
recognized as family hardware but safely does nothing until a CA profile is
added.

The image uses Fedora 44 Mutter's built-in `gdctl` for transient GNOME Wayland
layouts. It does not install another Mutter or a separate display-config tool.
With the detachable keyboard connected over USB, automatic policy selects the
upper display only. When detached, it selects both displays in a stacked
layout. Rotation from `monitor-sensor` supports normal, bottom-up, left-up,
and right-up layouts. The service uses only relative `gdctl` placement, so it
does not hard-code pixel offsets or persist automatic changes to GNOME's saved
monitor configuration.

Touchscreen and tablet mappings are applied for `04f3:425b` (upper) and
`04f3:425a` (lower), and the supplied libinput quirk enables detachable
keyboard/touchpad palm rejection. Root-only support is limited to normalized
OLED brightness synchronization and the standard battery charge threshold,
which defaults to 80%. A system-sleep hook re-syncs brightness after resume;
the hook also signals a global user `.path` unit, whose GNOME-side service
re-evaluates keyboard state, layout, touch mapping, and orientation after
resume.

Automatic dock, undock, rotation, and resume changes leave GNOME alone whenever
another DRM display is connected. Manual layouts require `--force` to override
that protection:

```bash
/usr/libexec/current-zenbook-duo check-hardware
/usr/libexec/current-zenbook-duo status
/usr/libexec/current-zenbook-duo top
/usr/libexec/current-zenbook-duo bottom
/usr/libexec/current-zenbook-duo both
/usr/libexec/current-zenbook-duo toggle
/usr/libexec/current-zenbook-duo --force both
```

Display connector, optional mode, and scale overrides live in
`/etc/current/zenbook-duo.conf`. `Scale=auto` uses the UX8406MA profile default
of `1.66667`, suitable for the common 3K panel; administrators can set another
valid GNOME scale explicitly.

## Installation

```bash
sudo bootc switch ghcr.io/noahgiroux/fedora-gnome-ux8406:latest
sudo systemctl reboot
```

## Hardware-test gates

Keyboard backlight control and hotkey remapping remain phase-two work. This
image intentionally does not add `asusctl`, `supergfxctl`, passwordless sudo,
DKMS, custom kernels, patched Mutter/libwacom, or out-of-tree audio/camera/NPU
components. Lower-touch inhibition is also deferred until it can be proven
safe without broad privileged control.

PSR and Intel `xe` remain diagnostics, not defaults. On the physical machine,
collect evidence before changing kernel policy:

```bash
lspci -nnk | grep -A4 -Ei 'VGA|Display'
lsmod | grep -E '^(i915|xe)\b'
journalctl -b -k | grep -Ei 'i915|xe|drm|psr|panel'
```

Before relying on this image, test both OLEDs, connector discovery and scale,
external-monitor protection, USB and Bluetooth keyboard workflows, touch/pen,
rotation axes, brightness after suspend/resume, charge threshold availability,
speakers, internal and headset microphones, IPU6 camera, Intel `ivpu`, and
suspend/resume. The analog headset microphone and any PSR-related behavior
still require a real UX8406MA running the built image.

Run the source checks with `./scripts/validate-ux8406.sh`; the GitHub Actions
matrix independently builds both hardware images and is the authoritative
BlueBuild recipe validation when the CLI is not installed locally.
