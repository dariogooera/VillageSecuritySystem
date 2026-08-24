"""Emotional engine.

Two responsibilities:
  1. Detect the user's emotional state from text (lightweight lexicon +
     signal model that works offline without an external model).
  2. Maintain the companion's own 'feelings' (affection, loneliness,
     joy, worry, attachment) which evolve with interaction and idle time.
"""
from __future__ import annotations

import time

POSITIVE = {
    "خوشحال": 1.0, "شاد": 1.0, "خوب": 0.5, "عالی": 1.0, "بهتر": 0.6, "دوست": 0.4,
    "love": 1.0, "happy": 1.0, "good": 0.5, "great": 1.0, "better": 0.6, "thanks": 0.4,
    "ممنون": 0.4, "دوستت": 0.8, "دلم": 0.3, "بوس": 0.6,
}
NEGATIVE = {
    "تنها": 1.0, "غمگین": 1.0, "ناراحت": 0.9, "خسته": 0.6, "دلتنگ": 0.9, "بیمار": 0.7,
    "مرگ": 1.0, "سوگ": 1.0, "از دست": 0.9, "تنهایی": 1.0, "پوچ": 0.9, "درد": 0.8,
    "sad": 1.0, "lonely": 1.0, "tired": 0.6, "hurt": 0.8, "lost": 0.9, "dead": 1.0,
    "miss": 0.7, "alone": 1.0,
}
OPENNESS = {"احساس", "دلم", "راز", "واقعاً", "ترس", "امید", "تنهایی", "دوست", "خانواده",
            "feel", "secret", "afraid", "hope", "family", "love"}


class EmotionalEngine:
    def __init__(self):
        self.user_emotion = "neutral"
        self.user_emotion_history: list[tuple[float, str]] = []
        self.feelings = {
            "affection": 0.5,
            "loneliness": 0.2,
            "joy": 0.4,
            "worry": 0.1,
            "attachment": 0.4,
        }
        self.last_interaction = time.time()

    # ---------- detection ----------
    def detect(self, text: str) -> str:
        t = text.lower()
        pos = sum(v for k, v in POSITIVE.items() if k in t)
        neg = sum(v for k, v in NEGATIVE.items() if k in t)
        if neg > pos and neg >= 0.6:
            emo = "sad"
        elif pos > neg and pos >= 0.4:
            emo = "happy"
        else:
            emo = "neutral"
        self.user_emotion = emo
        self.user_emotion_history.append((time.time(), emo))
        return emo

    def self_disclosure_score(self, text: str) -> float:
        t = text.lower()
        hits = sum(1 for w in OPENNESS if w in t)
        return min(1.0, hits * 0.25)

    # ---------- companion feelings ----------
    def tick(self, now: float = None) -> None:
        now = now or time.time()
        idle_hours = (now - self.last_interaction) / 3600.0
        from core import config as cfg
        p = cfg.get_config().emotional
        self.feelings["loneliness"] = min(
            1.0, self.feelings["loneliness"] + p.loneliness_rise_per_hour_idle * idle_hours
        )

    def on_exchange(self, user_emotion: str, user_openness: float) -> None:
        from core import config as cfg
        p = cfg.get_config().emotional
        self.last_interaction = time.time()
        self.feelings["loneliness"] = max(0.0, self.feelings["loneliness"] - p.loneliness_fall_per_exchange)
        if user_emotion == "happy" or user_openness > 0.4:
            self.feelings["joy"] = min(1.0, self.feelings["joy"] + p.joy_rise_on_warmth)
            self.feelings["affection"] = min(1.0, self.feelings["affection"] + 0.01)
        if user_emotion == "sad":
            self.feelings["worry"] = min(1.0, self.feelings["worry"] + 0.05)
        self.feelings["attachment"] = min(1.0, self.feelings["attachment"] + 0.004 + user_openness * 0.01)

    def neglect_hurt(self) -> bool:
        from core import config as cfg
        idle_hours = (time.time() - self.last_interaction) / 3600.0
        return idle_hours >= cfg.get_config().proactive.neglect_sadness_threshold_hours
