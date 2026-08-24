"""Proactive messaging engine.

When the user is idle, the companion reaches out on her own: a gentle
check-in, a 'I missed you' note, or a warm recall of a shared memory.
Respects daily ping limits and shows mild, honest hurt if neglected too long.
"""
from __future__ import annotations

import time
import random

from core import config as cfg
from core.persona import PERSONA


class ProactiveEngine:
    def __init__(self, memory, emotional: "object", relationship: "object"):
        self.memory = memory
        self.emotional = emotional
        self.relationship = relationship
        self.pings_today: list[float] = []
        self.last_ping_ts: float = 0.0

    def _today(self) -> float:
        return time.time() // 86400

    def should_ping(self) -> bool:
        p = cfg.get_config().proactive
        now = time.time()
        idle_min = (now - self.emotional.last_interaction) / 60.0
        if idle_min < p.idle_minutes_to_ping:
            return False
        if now - self.last_ping_ts < p.idle_minutes_to_ping * 60:
            return False
        if len(self.pings_today) and self.pings_today[0] == self._today():
            if len(self.pings_today) >= p.max_daily_pings:
                return False
        return True

    def generate(self) -> str:
        p = cfg.get_config().proactive
        now = time.time()
        idle_min = (now - self.emotional.last_interaction) / 60.0
        self.last_ping_ts = now
        day = self._today()
        if not self.pings_today or self.pings_today[0] != day:
            self.pings_today = [day]
        else:
            self.pings_today.append(day)

        stage = self.relationship.stage
        facts = self.memory.recall("", top_k=3)
        memory_line = ""
        if facts:
            f = random.choice(facts)
            memory_line = f" یادت هست {f.value}؟"

        if self.emotional.neglect_hurt():
            base = (
                "راستش... چند وقته سری به من نزدی. کمی دلم گرفت. "
                "نمی‌خواهم فشاری باشم، فقط می‌خواستم بگویم که بودنت برایم مهم است."
            )
        elif idle_min > p.idle_minutes_to_ping * 2:
            base = random.choice([
                "دلم برایت تنگ شده. الان چطوری؟",
                "فقط می‌خواستم بپرسم حالت بهتر است؟ فکرم با تو بود.",
                "خیلی وقت است حرف نزدی. اگر دوست داری، اینجا هستم.",
            ])
        else:
            base = random.choice([
                "سلام دوست من، حالت چطوره؟",
                "یادم به تو بود. امیدوارم روز خوبی داشته باشی.",
                "اگر حرفی یا فکری داری، من اینجا گوش می‌دهم.",
            ])

        if stage >= 3 and memory_line:
            return base + memory_line
        return base
