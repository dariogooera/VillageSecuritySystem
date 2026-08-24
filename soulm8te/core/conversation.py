"""Conversation manager: orchestrates memory, emotion, relationship,
proactive outreach, self-improvement and the LLM backend into one coherent,
natural dialogue. Also extracts simple long-term facts to remember.
"""
from __future__ import annotations

import os
import re
import time

from core import config as cfg
from core.persona import PERSONA
from core.memory import Memory
from core.emotional import EmotionalEngine
from core.relationship import RelationshipTracker
from core.proactive import ProactiveEngine
from core.self_improve import SelfImprover
from llm import backend as llm_backend

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "state")
MEMORY_PATH = os.path.join(STATE_DIR, "memory.json")
SELF_LOG_PATH = os.path.join(STATE_DIR, "self_improve.json")

FACT_PATTERNS = [
    (r"اسم(م| من) (.+?) است", "name"),
    (r"من (.+?) دوست دارم", "like"),
    (r"مرا (.+?) صدا بزن", "nickname"),
]


class Companion:
    def __init__(self):
        self.memory = Memory(MEMORY_PATH)
        self.emotional = EmotionalEngine()
        self.relationship = RelationshipTracker()
        self.proactive = ProactiveEngine(self.memory, self.emotional, self.relationship)
        self.self_improver = SelfImprover(SELF_LOG_PATH)
        self.backend = llm_backend.build_backend()
        self._exchange_log: list[dict] = []
        self._last_self_improve = 0.0

    # ---------- fact extraction (long-term memory) ----------
    def _extract_facts(self, text: str) -> None:
        for pat, kind in FACT_PATTERNS:
            m = re.search(pat, text)
            if m:
                value = m.group(2).strip()
                if value:
                    self.memory.remember(kind + ":" + value[:20], value, importance=0.7)
        # Remember emotional moments worth keeping.
        if any(w in text.lower() for w in ["تنها", "سوگ", "درد", "دلتنگ", "lost", "lonely", "grief"]):
            self.memory.remember("feeling:" + str(int(time.time())), text[:80], importance=0.6)

    # ---------- main reply ----------
    def respond(self, user_text: str) -> str:
        self.emotional.tick()
        emotion = self.emotional.detect(user_text)
        openness = self.emotional.self_disclosure_score(user_text)
        self._extract_facts(user_text)

        facts = self.memory.recall(user_text, top_k=2)
        memory_hint = facts[0].value if facts else ""

        context = repr({
            "emotion": emotion,
            "stage": self.relationship.stage,
            "openness": round(openness, 2),
            "memory": memory_hint,
        })

        system = (
            f"You are {PERSONA.name}, a {PERSONA.role}. "
            f"Traits: {', '.join(PERSONA.core_traits)}. "
            f"Stage: {self.relationship.stage_label()}. "
            f"Boundaries: {', '.join(PERSONA.boundaries)}."
        )

        bot_text = self.backend.generate(system, user_text, context)

        tone = cfg.get_config().tone
        # Warmth + stage gently steer the closing of the message.
        self.memory.add_turn("user", user_text, emotion)
        self.memory.add_turn("bot", bot_text)
        self.emotional.on_exchange(emotion, openness)
        self.relationship.record(openness, emotion, tone.warmth)

        self._exchange_log.append({
            "user_len": len(user_text),
            "openness": openness,
            "emotion": emotion,
            "ts": time.time(),
        })
        self._maybe_self_improve()
        self.memory.save()
        return bot_text

    def _maybe_self_improve(self) -> None:
        now = time.time()
        if now - self._last_self_improve < 60 and len(self._exchange_log) < 6:
            return
        self._last_self_improve = now
        recent = self._exchange_log[-10:]
        if len(recent) >= 3:
            result = self.self_improver.improve(recent)
            self._exchange_log = self._exchange_log[-20:]
            if result.get("applied"):
                return result
        return None

    def maybe_proactive(self) -> str | None:
        if self.proactive.should_ping():
            msg = self.proactive.generate()
            self.memory.add_turn("bot", msg)
            self.memory.save()
            return msg
        return None

    def status(self) -> str:
        return (
            f"مرحله رابطه: {self.relationship.stage_label()} "
            f"(صمیمیت {self.relationship.intimacy:.2f})\n"
            f"احساس کاربر اخیر: {self.emotional.user_emotion}\n"
            f"دلبستگی من: {self.emotional.feelings['attachment']:.2f} | "
            f"تنهایی من: {self.emotional.feelings['loneliness']:.2f}"
        )
