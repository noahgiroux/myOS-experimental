#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m py_compile \
  files/hardware/asus-zenbook-duo-ux8406/usr/libexec/current_zenbook_duo_lib.py \
  files/hardware/asus-zenbook-duo-ux8406/usr/libexec/current-zenbook-duo \
  files/hardware/asus-zenbook-duo-ux8406/usr/libexec/current-zenbook-duo-brightness \
  files/hardware/asus-zenbook-duo-ux8406/usr/libexec/current-zenbook-duo-charge-limit

python3 - <<'PY'
from pathlib import Path
import re

ux = Path('recipes/layers/hardware/asus-zenbook-duo-ux8406.yml').read_text()
package_block = ux.split('packages:', 1)[1].split('  - type:', 1)[0]
packages = re.findall(r'^        - (.+)$', package_block, re.M)
assert packages == ['gnome-monitor-config', 'iio-sensor-proxy', 'inotify-tools', 'libwacom-utils'], packages
for prohibited in ('asusctl', 'supergfxctl', 'power-profiles-daemon', 'akmods', 'dkms', 'kernel-devel', 'i915.enable_psr=0', 'python3-pyusb'):
    assert prohibited.lower() not in ux.lower(), prohibited
recipe = Path('recipes/images/workstation/gnome/fedora/ux8406.yml').read_text()
assert 'ghcr.io/pelagians/fedora-gnome' in recipe
assert 'broadcom-wl' not in recipe and 'broadcom-wl' not in ux
assert 'from-file: layers/hardware/broadcom-wl.yml' in Path('recipes/recipe.yml').read_text()
assert 'asus-zenbook-duo-ux8406.yml' not in Path('recipes/recipe.yml').read_text()
PY

if command -v bluebuild >/dev/null 2>&1; then
  bluebuild validate recipes/recipe.yml
  bluebuild validate recipes/images/workstation/gnome/fedora/ux8406.yml
  bluebuild generate -d recipes/images/workstation/gnome/fedora/ux8406.yml >/dev/null
else
  echo 'bluebuild not installed; skipped recipe validation/generation'
fi

if command -v systemd-analyze >/dev/null 2>&1; then
  unit_root="$(mktemp -d)"
  trap 'find "$unit_root" -depth -delete 2>/dev/null || true' EXIT
  mkdir -p "$unit_root/usr/lib/systemd/system" "$unit_root/usr/lib/systemd/user" "$unit_root/usr/libexec"
  cp files/hardware/asus-zenbook-duo-ux8406/usr/lib/systemd/system/*.service "$unit_root/usr/lib/systemd/system/"
  cp files/hardware/asus-zenbook-duo-ux8406/usr/lib/systemd/user/*.service "$unit_root/usr/lib/systemd/user/"
  cp files/hardware/asus-zenbook-duo-ux8406/usr/libexec/current-zenbook-duo* "$unit_root/usr/libexec/"
  printf '[Unit]\nDescription=validation target\n' > "$unit_root/usr/lib/systemd/system/sysinit.target"
  systemd-analyze verify --root="$unit_root" \
    "$unit_root/usr/lib/systemd/system/current-zenbook-duo-brightness.service" \
    "$unit_root/usr/lib/systemd/system/current-zenbook-duo-charge-limit.service"
fi

if command -v shellcheck >/dev/null 2>&1; then
  shellcheck scripts/validate-ux8406.sh
fi
