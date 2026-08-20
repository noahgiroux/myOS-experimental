#!/usr/bin/env python3
"""Small, dependency-free primitives shared by the UX8406 helpers.

The module deliberately keeps model data in /usr/lib/current/zenbook-duo/profiles;
new UX8406 variants can therefore be added without changing the policy code.
"""
from __future__ import annotations

import configparser
import glob
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

PROFILE_DIR = Path(os.environ.get("ZENBOOK_DUO_PROFILE_DIR", "/usr/lib/current/zenbook-duo/profiles"))
CONFIG_PATH = Path(os.environ.get("ZENBOOK_DUO_CONFIG", "/etc/current/zenbook-duo.conf"))


@dataclass(frozen=True)
class Profile:
    name: str
    vendor: str
    product: str
    keyboard: str
    upper_input: str
    lower_input: str
    top_connector: str
    bottom_connector: str
    mode_prefix: str
    panel_vendor: str
    panel_product: str
    panel_serial: str
    upper_backlight_patterns: tuple[str, ...]
    lower_backlight_patterns: tuple[str, ...]


def _profile(path: Path) -> Profile:
    parser = configparser.ConfigParser()
    parser.read(path)
    section = parser["Model"]
    split = lambda key: tuple(x.strip() for x in section.get(key, "").split(",") if x.strip())
    return Profile(path.stem, section["Vendor"], section["Product"], section["Keyboard"],
                   section["UpperInput"], section["LowerInput"], section["TopConnector"],
                   section["BottomConnector"], section["ModePrefix"], section["PanelVendor"],
                   section["PanelProduct"], section["PanelSerial"], split("UpperBacklightPatterns"),
                   split("LowerBacklightPatterns"))


def dmi_value(name: str, root: Path = Path("/sys/class/dmi/id")) -> str:
    try:
        return (root / name).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def family_product(product: str) -> bool:
    return product.upper().startswith("UX8406")


def load_profile(vendor: str | None = None, product: str | None = None,
                 profile_dir: Path = PROFILE_DIR) -> Profile | None:
    vendor = dmi_value("sys_vendor") if vendor is None else vendor
    product = dmi_value("product_name") if product is None else product
    for path in sorted(profile_dir.glob("*.conf")):
        try:
            profile = _profile(path)
        except (KeyError, configparser.Error, OSError):
            continue
        if profile.vendor == vendor and profile.product == product:
            return profile
    return None


def hardware_status(profile_dir: Path = PROFILE_DIR) -> tuple[bool, str]:
    vendor, product = dmi_value("sys_vendor"), dmi_value("product_name")
    if not family_product(product):
        return False, f"unsupported hardware: {vendor or '?'} / {product or '?'}"
    profile = load_profile(vendor, product, profile_dir)
    if profile is None:
        return False, f"UX8406 family detected ({product}), but no model profile is installed"
    return True, f"supported {profile.name}: {vendor} / {product}"


def _unwrap_variant(value: Any) -> Any:
    # busctl JSON normally returns a {type,data} object. Be liberal for fixtures.
    if isinstance(value, dict) and "data" in value:
        return value["data"]
    return value


def parse_mutter_state(value: Any) -> dict[str, Any]:
    value = _unwrap_variant(value)
    if isinstance(value, str):
        value = json.loads(value)
        value = _unwrap_variant(value)
    if not isinstance(value, list) or len(value) < 3:
        raise ValueError("unexpected Mutter DisplayConfig state")
    monitors, logical = [], []
    for monitor in value[1] or []:
        spec = monitor[0]
        modes = []
        for mode in monitor[1] or []:
            modes.append({"id": mode[0], "width": mode[1], "height": mode[2],
                          "refresh": mode[3], "preferred_scale": mode[4],
                          "preferred": bool(_unwrap_variant(mode[6]).get("is-current", False))
                          if isinstance(_unwrap_variant(mode[6]), dict) else False})
        monitors.append({"connector": spec[0], "vendor": spec[1], "product": spec[2],
                         "serial": spec[3], "modes": modes,
                         "internal": spec[0].startswith(("eDP", "LVDS", "DSI"))})
    for item in value[2] or []:
        outputs = []
        for spec in item[5] or []:
            outputs.append(tuple(spec[:4]))
        logical.append({"x": item[0], "y": item[1], "scale": item[2],
                        "transform": item[3], "primary": bool(item[4]), "outputs": outputs})
    return {"monitors": monitors, "logical_monitors": logical, "properties": value[3] if len(value) > 3 else {}}


def mutter_state() -> dict[str, Any]:
    result = subprocess.run([
        "busctl", "--user", "--json=short", "call", "org.gnome.Mutter.DisplayConfig",
        "/org/gnome/Mutter/DisplayConfig", "org.gnome.Mutter.DisplayConfig", "GetCurrentState"
    ], check=True, capture_output=True, text=True)
    return parse_mutter_state(result.stdout)


def read_config(path: Path = CONFIG_PATH) -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.read(path)
    return parser


def effective_connectors(profile: Profile, config: configparser.ConfigParser) -> tuple[str, str]:
    section = config["Display"] if config.has_section("Display") else {}
    return section.get("TopConnector", "").strip() or profile.top_connector, section.get("BottomConnector", "").strip() or profile.bottom_connector


def has_external_monitor(state: dict[str, Any], internal: Iterable[str]) -> bool:
    internal = set(internal)
    return any(m["connector"] not in internal for m in state.get("monitors", []))


def preferred_mode(monitor: dict[str, Any], prefix: str, override: str = "") -> str | None:
    modes = monitor.get("modes", [])
    if override:
        for mode in modes:
            if mode["id"] == override:
                return override
    for mode in modes:
        identity = f'{mode["width"]}x{mode["height"]}@{mode["refresh"]:g}'
        if identity.startswith(prefix) or mode["id"].startswith(prefix):
            return mode["id"]
    for mode in modes:
        if mode.get("preferred"):
            return mode["id"]
    return modes[0]["id"] if modes else None


def layout_plan(state: dict[str, Any], profile: Profile, orientation: str = "normal",
                attached: bool = False, config: configparser.ConfigParser | None = None) -> list[dict[str, Any]]:
    config = config or configparser.ConfigParser()
    top, bottom = effective_connectors(profile, config)
    monitors = {m["connector"]: m for m in state.get("monitors", [])}
    if top not in monitors or bottom not in monitors:
        return []
    section = config["Display"] if config.has_section("Display") else {}
    mode_override = section.get("Mode", "").strip()
    scale_value = section.get("Scale", "auto").strip()
    def panel(connector: str, transform: str, x: int, y: int) -> dict[str, Any]:
        mon = monitors[connector]
        mode = preferred_mode(mon, profile.mode_prefix, mode_override)
        scale = next((l["scale"] for l in state.get("logical_monitors", []) if connector in [o[0] for o in l["outputs"]]), 1)
        if scale_value != "auto":
            try: scale = float(scale_value)
            except ValueError: pass
        return {"connector": connector, "mode": mode, "x": x, "y": y, "scale": scale, "transform": transform}
    transform = {"normal": "normal", "bottom-up": "180", "left-up": "90", "right-up": "270"}.get(orientation, "normal")
    if attached:
        return [panel(top, transform, 0, 0)]
    top_mode = preferred_mode(monitors[top], profile.mode_prefix, mode_override)
    top_size = next(((m["width"], m["height"]) for m in monitors[top]["modes"] if m["id"] == top_mode), None)
    if top_size is None:
        return []
    rotated_span = top_size[1]
    if orientation == "bottom-up":
        return [panel(bottom, "180", 0, 0), panel(top, "180", 0, -rotated_span)]
    if orientation == "left-up":
        return [panel(bottom, "90", 0, 0), panel(top, "90", rotated_span, 0)]
    if orientation == "right-up":
        return [panel(top, "270", 0, 0), panel(bottom, "270", rotated_span, 0)]
    return [panel(top, "normal", 0, 0), panel(bottom, "normal", 0, top_size[1])]


def brightness_value(upper: int, upper_max: int, lower_max: int) -> int:
    if upper_max <= 0 or lower_max < 0:
        raise ValueError("invalid backlight range")
    return max(0, min(lower_max, round(upper / upper_max * lower_max)))


def validate_charge_limit(value: str | int) -> int:
    number = int(value)
    if not 1 <= number <= 100:
        raise ValueError("ChargeLimit must be between 1 and 100")
    return number


def find_backlight(patterns: Iterable[str], root: Path = Path("/sys/class/backlight")) -> Path | None:
    for pattern in patterns:
        matches = sorted(root.glob(pattern))
        if matches:
            return matches[0]
    return None


def keyboard_attached(profile: Profile, root: Path = Path("/sys/bus/usb/devices")) -> bool:
    vendor, product = profile.keyboard.lower().split(":", 1)
    for path in root.glob("*"):
        try:
            if (path / "idVendor").read_text().strip().lower() == vendor and (path / "idProduct").read_text().strip().lower() == product:
                return True
        except OSError:
            continue
    return False


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, text=True, capture_output=True)
