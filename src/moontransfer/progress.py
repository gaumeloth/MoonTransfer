from __future__ import annotations

import re
from dataclasses import dataclass


ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
SIZE_UNIT_RE = r"(?:[KMGTPE]i?B|[KMGTPE]?B)"
TOTAL_RE = re.compile(
    rf"\b(?:Sending|Receiving)(?:\s+\d+\s+files)?(?:\s+'.*?')?"
    rf"\s+\((?P<value>\d+(?:\.\d+)?)\s*(?P<unit>{SIZE_UNIT_RE})\)",
    re.IGNORECASE,
)
TRANSFER_PROGRESS_RE = re.compile(
    rf"\(\s*"
    rf"(?P<transferred>\d+(?:\.\d+)?)\s*"
    rf"(?P<transferred_unit>{SIZE_UNIT_RE})?\s*/\s*"
    rf"(?P<total>\d+(?:\.\d+)?)\s*"
    rf"(?P<total_unit>{SIZE_UNIT_RE})"
    rf"(?:,\s*(?P<speed>\d+(?:\.\d+)?)\s*"
    rf"(?P<speed_unit>{SIZE_UNIT_RE}/s))?"
    rf"\s*\)",
    re.IGNORECASE,
)
PERCENT_RE = re.compile(r"\b(?P<percent>\d{1,3})%")


@dataclass(frozen=True)
class TransferProgressSample:
    percent: int | None = None
    transferred_bytes: int | None = None
    total_bytes: int | None = None
    speed_bps: float | None = None


def format_file_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"

    size = float(num_bytes)
    for unit in ("KiB", "MiB", "GiB", "TiB"):
        size /= 1024
        if size < 1024:
            return f"{size:.1f} {unit}"

    return f"{size:.1f} PiB"


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"

    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def format_transfer_rate(bytes_per_second: float | None) -> str:
    if bytes_per_second is None or bytes_per_second <= 0:
        return "-"
    return f"{format_file_size(int(bytes_per_second))}/s"


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def parse_size_value(value: str, unit: str) -> int:
    unit = unit.strip()
    binary_units = {
        "KiB": 1024,
        "MiB": 1024**2,
        "GiB": 1024**3,
        "TiB": 1024**4,
        "PiB": 1024**5,
        "EiB": 1024**6,
    }
    decimal_units = {
        "B": 1,
        "KB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "TB": 1000**4,
        "PB": 1000**5,
        "EB": 1000**6,
    }

    multiplier = None
    for name, value_multiplier in binary_units.items():
        if unit.lower() == name.lower():
            multiplier = value_multiplier
            break

    if multiplier is None:
        multiplier = decimal_units.get(unit.upper())

    if not multiplier:
        raise ValueError(f"Unità dimensione non supportata: {unit}")

    return int(float(value) * multiplier)


def parse_announced_transfer_total(line: str) -> int | None:
    match = TOTAL_RE.search(strip_ansi(line))
    if not match:
        return None

    return parse_size_value(match.group("value"), match.group("unit"))


def parse_transfer_progress(line: str) -> TransferProgressSample | None:
    clean_line = strip_ansi(line).strip()
    match = TRANSFER_PROGRESS_RE.search(clean_line)
    if not match:
        return None

    percent_match = PERCENT_RE.search(clean_line)
    percent = None
    if percent_match:
        percent = max(0, min(100, int(percent_match.group("percent"))))

    total_unit = match.group("total_unit")
    transferred_unit = match.group("transferred_unit") or total_unit
    transferred_bytes = parse_size_value(
        match.group("transferred"),
        transferred_unit,
    )
    total_bytes = parse_size_value(match.group("total"), total_unit)

    speed_bps = None
    if match.group("speed") and match.group("speed_unit"):
        speed_unit = match.group("speed_unit").removesuffix("/s")
        speed_bps = float(parse_size_value(match.group("speed"), speed_unit))

    return TransferProgressSample(
        percent=percent,
        transferred_bytes=transferred_bytes,
        total_bytes=total_bytes,
        speed_bps=speed_bps,
    )
