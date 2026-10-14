"""Validated preferences with atomic, per-user persistence."""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path


@dataclass
class Settings:
    theme: str = "system"
    accent: str = "mint"
    size: str = "compact"
    units: str = "bits"
    interval: float = 1.0
    opacity: float = 1.0
    corner_radius: int = 12
    topmost: bool = True
    graphs: bool = True
    adapter: str = "auto"
    x: int | None = None
    y: int | None = None

    @classmethod
    def from_dict(cls, data: object) -> Settings:
        result = cls()
        if not isinstance(data, dict):
            return result
        choices = {
            "theme": ("system", "dark", "light"),
            "accent": ("mint", "blue", "violet", "peach"),
            "size": ("mini", "compact", "comfortable"),
            "units": ("bits", "bytes"),
        }
        for name, allowed in choices.items():
            if isinstance(data.get(name), str) and data[name] in allowed:
                setattr(result, name, data[name])
        for name, low, high in (("interval", 0.5, 3.0), ("opacity", 0.65, 1.0)):
            value = data.get(name)
            if type(value) in (int, float):
                try:
                    if math.isfinite(value):
                        setattr(result, name, min(high, max(low, float(value))))
                except OverflowError:
                    pass
        for name in ("topmost", "graphs"):
            if type(data.get(name)) is bool:
                setattr(result, name, data[name])
        if type(data.get("corner_radius")) is int:
            result.corner_radius = min(24, max(0, data["corner_radius"]))
        if isinstance(data.get("adapter"), str) and 0 < len(data["adapter"]) < 300:
            result.adapter = data["adapter"]
        # Keep negative coordinates: monitors can be left/above the primary one.
        if all(type(data.get(name)) is int and abs(data[name]) < 1_000_000 for name in ("x", "y")):
            result.x, result.y = data["x"], data["y"]
        return result


def default_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "NetPulse" / "settings.json"


def load_settings(path: Path) -> Settings:
    try:
        return Settings.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, RecursionError):
        return Settings()


def save_settings(settings: Settings, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
    temporary.replace(path)


def reset_appearance(settings: Settings) -> None:
    defaults = Settings()
    for field in fields(settings):
        if field.name not in ("adapter", "x", "y"):
            setattr(settings, field.name, getattr(defaults, field.name))
