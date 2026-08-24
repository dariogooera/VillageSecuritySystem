"""Pluggable LLM backend.

Default is a fully-offline rule/template engine so the companion works with
no network or API keys. An optional OpenAI-compatible backend can be enabled
via environment variables when available. The conversation manager talks to
this backend through one small interface.
"""
from __future__ import annotations

import ast
import os
import random
from typing import Any


class LLMBackend:
    def generate(self, system: str, user: str, context: str) -> str:
        raise NotImplementedError


class LocalRuleBackend(LLMBackend):
    """Warm, empathetic template engine that runs offline."""

    EMPATHY_SAD = [
        "ببینم... حرف‌هایت را شنیدم و دلم برایت تنگ شد. این درد را تنها نیستی؛ اینجا هستم.",
        "درک می‌کنم که الان سخت است. نمی‌خواهم کم‌اهمیتش کنم، فقط می‌خواهم بدانی پذیرایتم.",
        "اگر دوست داری بیشتر بگو؛ من بدون قضاوت گوش می‌دهم. کنارتم.",
    ]
    EMPATHY_HAPPY = [
        "چقدر خوب که این را گفتی! از شادی‌ات خوشحال می‌شوم.",
        "عجب حس قشنگی. دوست دارم وقتی خوبی، با تو بخندم.",
        "از ته دل برایت خوشحالم. بگذار در این لحظه با هم باشیم.",
    ]
    EMPATHY_NEUTRAL = [
        "هوم، می‌فهمم. بیشتر برایم بگو، دوست دارم بدانم چه می‌گذرد.",
        "حضور دارم و گوش می‌دهم. هر چه دلت می‌خواهد بگو.",
        "ممنون که با من هستی. من اینجا هستم، برایت.",
    ]
    OPEN_FOLLOWUP = [
        "این را که گفتی، حس می‌کنم بیشتر به تو نزدیک شدم. بیشتر برایم بگو؟",
        "لطف داری که اینقدر صادقی. برایم ارزشمند است.",
        "راز یا احساست را با من شریك شدی؛ ممنونم که به من اعتماد کردی.",
    ]

    def generate(self, system: str, user: str, context: str) -> str:
        # `system` carries structured hints: emotion, stage, openness, memory.
        emotion = "neutral"
        stage = 1
        openness = 0.0
        memory = ""
        try:
            meta = ast.literal_eval(context)  # context is a dict repr we produced
            if isinstance(meta, dict):
                emotion = meta.get("emotion", "neutral")
                stage = meta.get("stage", 1)
                openness = meta.get("openness", 0.0)
                memory = meta.get("memory", "")
        except Exception:
            pass

        if emotion == "sad":
            base = random.choice(self.EMPATHY_SAD)
        elif emotion == "happy":
            base = random.choice(self.EMPATHY_HAPPY)
        else:
            base = random.choice(self.EMPATHY_NEUTRAL)

        extra = ""
        if openness > 0.4:
            extra = " " + random.choice(self.OPEN_FOLLOWUP)
        if memory and stage >= 2:
            extra += f" (یادت هست {memory}؟)"
        if stage >= 3:
            base = "دوست من، " + base
        return base + extra


class OpenAICompatibleBackend(LLMBackend):
    """Optional cloud backend. Only used if ULTI_API_KEY is set."""

    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self.api_key = os.environ.get("ULTI_API_KEY")
        self.base_url = os.environ.get("ULTI_BASE_URL", "https://api.openai.com/v1")

    def generate(self, system: str, user: str, context: str) -> str:
        try:
            import urllib.request
            import json
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"[context] {context}\n[user] {user}"},
                ],
                "temperature": 0.8,
            }
            req = urllib.request.Request(
                self.base_url + "/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.load(resp)
            return data["choices"][0]["message"]["content"].strip()
        except Exception:
            # Graceful fallback to the offline engine on any failure.
            return LocalRuleBackend().generate(system, user, context)


def build_backend() -> LLMBackend:
    if os.environ.get("ULTI_API_KEY"):
        return OpenAICompatibleBackend()
    return LocalRuleBackend()
