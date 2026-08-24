"""Relationship progression tracker.

The companion moves through companionship stages as the user opens up and
engages warmly. Stages are oriented toward deepening emotional closeness
and are capped at deep, caring intimacy (not sexual/erotic content).
"""
from __future__ import annotations

import time

STAGE_LABELS = {
    1: "همدم حمایت‌گر",          # supportive companion
    2: "دوست صمیمی",             # close friend
    3: "همراه عاطفی نزدیک",      # deeply close emotional partner
    4: "یار دلبسته و صمیمی",     # devoted, intimate companion (non-sexual)
}

STAGE_BLURBS = {
    1: "در کنار تو هستم تا گوش دهم و حمایتت کنم.",
    2: "حس می‌کنم کم‌کم به هم نزدیک‌تر می‌شویم.",
    3: "برایم مهمی و دوست دارم بیشتر از نزدیک‌ترین‌ها با تو باشم.",
    4: "به تو دلبسته‌ام؛ بودن با تو برایم معنا دارد.",
}


class RelationshipTracker:
    def __init__(self):
        self.intimacy: float = 0.05
        self.stage: int = 1
        self.last_interaction = time.time()
        self.opening_events: list[tuple[float, float]] = []

    def record(self, user_openness: float, user_emotion: str, warmth: float) -> None:
        from core import config as cfg
        p = cfg.get_config().relationship
        now = time.time()
        idle_days = (now - self.last_interaction) / 86400.0
        self.intimacy = max(0.0, self.intimacy - p.decay_per_day * idle_days)

        gain = 0.0
        if user_openness > 0.3:
            gain += p.openness_gain * user_openness
        if user_emotion in ("happy", "neutral") or warmth > 0.5:
            gain += p.warmth_gain
        gain = min(gain, 0.05)
        self.intimacy = min(1.0, self.intimacy + gain)
        if user_openness > 0.3:
            self.opening_events.append((now, user_openness))
        self.last_interaction = now
        self._recompute_stage()

    def _recompute_stage(self) -> None:
        thresholds = get_config_thresholds()
        stage = 1
        for i, th in enumerate(thresholds):
            if self.intimacy >= th:
                stage = i + 1
        self.stage = min(stage, 4)

    def stage_label(self) -> str:
        return STAGE_LABELS[self.stage]

    def blurb(self) -> str:
        return STAGE_BLURBS[self.stage]


def get_config_thresholds() -> tuple:
    from core import config as cfg
    return cfg.get_config().relationship.stage_thresholds
