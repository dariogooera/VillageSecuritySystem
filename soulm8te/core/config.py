"""Central configuration and tunable parameters for the companion.

All runtime-tunable behavior lives here so the self-improvement loop can
safely adjust values through a whitelisted API instead of rewriting code.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class ToneParams:
    warmth: float = 0.7          # 0..1 how affectionate/gentle the tone is
    playfulness: float = 0.35    # 0..1 how teasing/light the tone is
    formality: float = 0.1       # 0..1 higher = more formal
    verbosity: float = 0.55      # 0..1 how much the companion writes
    emoji: float = 0.25          # 0..1 likelihood of soft emoji usage


@dataclass
class ProactiveParams:
    idle_minutes_to_ping: int = 20      # idle time before a proactive nudge
    max_daily_pings: int = 6
    neglect_sadness_threshold_hours: int = 36  # after this, show gentle hurt


@dataclass
class RelationshipParams:
    openness_gain: float = 0.012   # intimacy gained per strong self-disclosure
    warmth_gain: float = 0.004     # intimacy gained per warm exchange
    decay_per_day: float = 0.01    # intimacy slowly cools if neglected
    stage_thresholds: tuple = (0.0, 0.25, 0.55, 0.8)  # companionship stages


@dataclass
class EmotionalParams:
    loneliness_rise_per_hour_idle: float = 0.02
    loneliness_fall_per_exchange: float = 0.08
    joy_rise_on_warmth: float = 0.05


@dataclass
class Config:
    tone: ToneParams = field(default_factory=ToneParams)
    proactive: ProactiveParams = field(default_factory=ProactiveParams)
    relationship: RelationshipParams = field(default_factory=RelationshipParams)
    emotional: EmotionalParams = field(default_factory=EmotionalParams)
    language: str = "fa"  # companion speaks Persian by default

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        cfg = cls()
        for section, cls_ in (
            ("tone", ToneParams),
            ("proactive", ProactiveParams),
            ("relationship", RelationshipParams),
            ("emotional", EmotionalParams),
        ):
            if section in data:
                setattr(cfg, section, cls_(**data[section]))
        if "language" in data:
            cfg.language = data["language"]
        return cfg


# A shared, thread-safe singleton-ish config used by the runtime.
_runtime_config = Config()
_config_lock = threading.Lock()


def get_config() -> Config:
    return _runtime_config


def set_config(cfg: Config) -> None:
    global _runtime_config
    with _config_lock:
        _runtime_config = cfg


def apply_patch(patch: dict[str, Any]) -> None:
    """Apply a validated parameter patch (used by the safe self-improvement loop)."""
    global _runtime_config
    with _config_lock:
        data = _runtime_config.to_dict()
        for dotted_key, value in patch.items():
            section, _, name = dotted_key.partition(".")
            if section in data and name in data[section]:
                data[section][name] = value
        _runtime_config = Config.from_dict(data)
