#!/usr/bin/env python3
"""Dependency-free UX8406 policy and command construction helpers."""
from __future__ import annotations

import configparser
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

PROFILE_DIR = Path(os.environ.get("ZENBOOK_DUO_PROFILE_DIR", "/usr/lib/current/zenbook-duo/profiles"))
CONFIG_PATH = Path(os.environ.get("ZENBOOK_DUO_CONFIG", "/etc/current/zenbook-duo.conf"))
DRM_ROOT = Path(os.environ.get("ZENBOOK_DUO_DRM_ROOT", "/sys/class/drm"))
DMI_ROOT = Path(os.environ.get("ZENBOOK_DUO_DMI_ROOT", "/sys/class/dmi/id"))


@dataclass(frozen=True)
class Profile:
    name: str
    vendor: str
    board: str
    keyboard: str
    upper_input: str
    lower_input: str
    top_connector: str
    bottom_connector: str
    default_scale: float
    panel_vendor: str
    panel_product: str
    panel_serial: str
    upper_backlight_patterns: tuple[str, ...]
    lower_backlight_patterns: tuple[str, ...]


def _profile(path: Path) -> Profile:
    parser = configparser.ConfigParser()
    parser.read(path)
    section = parser["Model"]
    split = lambda key: tuple(value.strip() for value in section.get(key, "").split(",") if value.strip())
    return Profile(
        name=path.stem,
        vendor=section["Vendor"],
        board=section["Board"],
        keyboard=section["Keyboard"],
        upper_input=section["UpperInput"],
        lower_input=section["LowerInput"],
        top_connector=section["TopConnector"],
        bottom_connector=section["BottomConnector"],
        default_scale=float(section.get("DefaultScale", "1.66667")),
        panel_vendor=section["PanelVendor"],
        panel_product=section["PanelProduct"],
        panel_serial=section["PanelSerial"],
        upper_backlight_patterns=split("UpperBacklightPatterns"),
        lower_backlight_patterns=split("LowerBacklightPatterns"),
    )


def dmi_value(name: str, root: Path = DMI_ROOT) -> str:
    try:
        return (root / name).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def model_key(vendor: str, board_name: str, product_name: str) -> str | None:
    """Return the recognized UX8406 board token, preferring DMI board_name."""
    if vendor != "ASUSTeK COMPUTER INC.":
        return None
    for value in (board_name.upper(), product_name.upper()):
        match = re.search(r"UX8406(?:MA|CA)", value)
        if match:
            return match.group(0)
    return None


def load_profile(vendor: str | None = None, board_name: str | None = None,
                 product_name: str | None = None, profile_dir: Path = PROFILE_DIR,
                 dmi_root: Path = DMI_ROOT) -> Profile | None:
    vendor = dmi_value("sys_vendor", dmi_root) if vendor is None else vendor
    board_name = dmi_value("board_name", dmi_root) if board_name is None else board_name
    product_name = dmi_value("product_name", dmi_root) if product_name is None else product_name
    key = model_key(vendor, board_name, product_name)
    if key is None:
        return None
    for path in sorted(profile_dir.glob("*.conf")):
        try:
            profile = _profile(path)
        except (KeyError, ValueError, configparser.Error, OSError):
            continue
        if profile.vendor == vendor and profile.board == key:
            return profile
    return None


def hardware_status(profile_dir: Path = PROFILE_DIR, dmi_root: Path = DMI_ROOT) -> tuple[bool, str]:
    vendor = dmi_value("sys_vendor", dmi_root)
    board = dmi_value("board_name", dmi_root)
    product = dmi_value("product_name", dmi_root)
    key = model_key(vendor, board, product)
    if key is None:
        return False, f"unsupported hardware: {vendor or '?'} / {board or product or '?'}"
    profile = load_profile(vendor, board, product, profile_dir, dmi_root)
    if profile is None:
        return False, f"UX8406 family detected ({key}), but no {key} profile is installed"
    return True, f"supported {profile.name}: {vendor} / {board or product}"


def read_config(path: Path = CONFIG_PATH) -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.read(path)
    return parser


def effective_connectors(profile: Profile, config: configparser.ConfigParser) -> tuple[str, str]:
    section = config["Display"] if config.has_section("Display") else {}
    return (section.get("TopConnector", "").strip() or profile.top_connector,
            section.get("BottomConnector", "").strip() or profile.bottom_connector)


def effective_scale(profile: Profile, config: configparser.ConfigParser) -> float:
    value = config.get("Display", "Scale", fallback="auto").strip()
    if value.lower() == "auto":
        return profile.default_scale
    try:
        scale = float(value)
    except ValueError:
        return profile.default_scale
    return scale if scale > 0 else profile.default_scale


def connected_connectors(root: Path = DRM_ROOT) -> set[str]:
    connected: set[str] = set()
    for status in root.glob("*/status"):
        try:
            if status.read_text().strip() != "connected":
                continue
        except OSError:
            continue
        name = status.parent.name
        match = re.match(r"^card\d+-(.+)$", name)
        if match:
            connected.add(match.group(1))
    return connected


def has_external_monitor(connected: Iterable[str], internal: Iterable[str]) -> bool:
    return bool(set(connected) - set(internal))


def panels_available(connected: Iterable[str], top: str, bottom: str, root_exists: bool = True) -> bool:
    # A missing DRM tree is treated as unavailable. This prevents a login race
    # from writing an arbitrary configuration before DRM devices exist.
    return root_exists and {top, bottom}.issubset(set(connected))


def transform_for(orientation: str) -> str:
    return {"normal": "normal", "bottom-up": "180", "left-up": "90", "right-up": "270"}.get(orientation, "normal")


def layout_monitors(kind: str, orientation: str, top: str, bottom: str) -> list[dict[str, str | bool]]:
    """Describe relative gdctl logical monitors without fixed pixel offsets."""
    transform = transform_for(orientation)
    if kind == "top":
        return [{"connector": top, "primary": True, "transform": transform}]
    if kind == "bottom":
        return [{"connector": bottom, "primary": True, "transform": transform}]
    if kind != "both":
        raise ValueError(f"unknown layout kind: {kind}")
    if orientation == "bottom-up":
        return [
            {"connector": bottom, "primary": True, "transform": "180"},
            {"connector": top, "transform": "180", "above": bottom},
        ]
    if orientation == "left-up":
        return [
            {"connector": bottom, "primary": True, "transform": "90"},
            {"connector": top, "transform": "90", "right_of": bottom},
        ]
    if orientation == "right-up":
        return [
            {"connector": top, "primary": True, "transform": "270"},
            {"connector": bottom, "transform": "270", "right_of": top},
        ]
    return [
        {"connector": top, "primary": True, "transform": "normal"},
        {"connector": bottom, "transform": "normal", "below": top},
    ]


def build_gdctl_command(profile: Profile, kind: str, orientation: str,
                        config: configparser.ConfigParser, scale_override: float | None = None) -> list[str]:
    top, bottom = effective_connectors(profile, config)
    mode = config.get("Display", "Mode", fallback="").strip()
    command = ["gdctl", "set", "--layout-mode", "logical"]
    for logical in layout_monitors(kind, orientation, top, bottom):
        command.extend(["--logical-monitor", "--monitor", str(logical["connector"])])
        if mode:
            command.extend(["--mode", mode])
        if logical.get("primary"):
            command.append("--primary")
        scale = effective_scale(profile, config) if scale_override is None else scale_override
        command.extend(["--scale", f"{scale:g}", "--transform", str(logical["transform"])])
        for option, flag in (("below", "--below"), ("above", "--above"),
                             ("left_of", "--left-of"), ("right_of", "--right-of")):
            if option in logical:
                command.extend([flag, str(logical[option])])
    return command


def active_internal_connectors(gdctl_show: str, known: Iterable[str]) -> set[str]:
    """Read connector mentions from gdctl's logical-monitor sections only."""
    active: set[str] = set()
    logical_sections = re.split(r"(?im)^.*logical monitor\s*#[^\n]*\n", gdctl_show)[1:]
    for section in logical_sections:
        for connector in known:
            if re.search(rf"(?<![A-Za-z0-9_-]){re.escape(connector)}(?![A-Za-z0-9_-])", section):
                active.add(connector)
    return active


def toggle_target(active: Iterable[str], top: str, bottom: str) -> str:
    active = set(active)
    return "top" if {top, bottom}.issubset(active) else "both"


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
            if ((path / "idVendor").read_text().strip().lower() == vendor and
                    (path / "idProduct").read_text().strip().lower() == product):
                return True
        except OSError:
            continue
    return False


def dock_state_changed(previous_attached: bool, current_attached: bool) -> bool:
    return previous_attached != current_attached
