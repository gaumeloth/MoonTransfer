from __future__ import annotations

from pathlib import Path

from kivy.utils import get_color_from_hex


def color(value: str) -> tuple[float, float, float, float]:
    return tuple(get_color_from_hex(value))


BACKGROUND = color("#0B0D12")
SURFACE = color("#141820")
SURFACE_ALT = color("#1A1F29")
SURFACE_STRONG = color("#222936")
SURFACE_DISABLED = color("#171B23")
BORDER = color("#2C3441")
BORDER_STRONG = color("#3A4555")

TEXT = color("#F4F6FA")
TEXT_MUTED = color("#A5ADBA")
TEXT_SUBTLE = color("#747E8C")
TEXT_DISABLED = color("#626B78")

PRIMARY = color("#5068D8")
PRIMARY_PRESSED = color("#4055B7")
PRIMARY_SOFT = color("#20294F")
PRIMARY_TEXT = color("#FFFFFF")

SUCCESS = color("#42C487")
SUCCESS_SOFT = color("#143326")
WARNING = color("#E8AE4A")
WARNING_SOFT = color("#382B14")
ERROR = color("#F06A70")
ERROR_SOFT = color("#3A1B20")

TRANSPARENT = (0.0, 0.0, 0.0, 0.0)
SCRIM = (0.0, 0.0, 0.0, 0.72)

ICON_ROOT = Path(__file__).with_name("assets") / "icons"


def icon_path(name: str) -> str:
    return str(ICON_ROOT / f"{name}.png")
