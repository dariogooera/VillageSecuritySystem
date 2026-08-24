"""Multi-layer memory: short-term (recent turns), mid-term (summaries),
and long-term (persistent facts, preferences, important memories).

Everything is persisted to a JSON file so the companion survives restarts
and can operate offline.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Turn:
    role: str          # "user" | "bot"
    text: str
    ts: float
    emotion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"role": self.role, "text": self.text, "ts": self.ts, "emotion": self.emotion}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Turn":
        return cls(d["role"], d["text"], d.get("ts", time.time()), d.get("emotion", ""))


@dataclass
class LongTermFact:
    key: str
    value: str
    ts: float
    importance: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "value": self.value, "ts": self.ts, "importance": self.importance}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LongTermFact":
        return cls(d["key"], d["value"], d.get("ts", time.time()), d.get("importance", 0.5))


class Memory:
    def __init__(self, path: str):
        self.path = path
        self.short_term: list[Turn] = []
        self.mid_term: list[dict[str, Any]] = []   # {"summary","ts","topics":[]}
        self.long_term: dict[str, LongTermFact] = {}
        self._load()

    # ---------- persistence ----------
    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.short_term = [Turn.from_dict(t) for t in data.get("short_term", [])]
            self.mid_term = data.get("mid_term", [])
            self.long_term = {k: LongTermFact.from_dict(v) for k, v in data.get("long_term", {}).items()}
        except Exception:
            # Corrupt state should never crash the companion.
            pass

    def save(self) -> None:
        data = {
            "short_term": [t.to_dict() for t in self.short_term],
            "mid_term": self.mid_term,
            "long_term": {k: v.to_dict() for k, v in self.long_term.items()},
        }
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    # ---------- short term ----------
    def add_turn(self, role: str, text: str, emotion: str = "", max_len: int = 24) -> None:
        self.short_term.append(Turn(role, text, time.time(), emotion))
        if len(self.short_term) > max_len:
            # Move the oldest turn into mid-term memory as a summarized echo.
            old = self.short_term.pop(0)
            self._summarize_to_mid(old)

    def _summarize_to_mid(self, turn: Turn) -> None:
        self.mid_term.append({
            "summary": f"{turn.role} said: {turn.text[:120]}",
            "ts": turn.ts,
            "topics": [],
        })
        self.mid_term = self.mid_term[-60:]

    def recent_context(self, n: int = 8) -> list[Turn]:
        return self.short_term[-n:]

    # ---------- long term ----------
    def remember(self, key: str, value: str, importance: float = 0.5) -> None:
        self.long_term[key] = LongTermFact(key, value, time.time(), importance)
        self.save()

    def recall(self, query: str, top_k: int = 4) -> list[LongTermFact]:
        q = query.lower()
        scored = []
        for fact in self.long_term.values():
            score = fact.importance
            if q:
                for word in q.split():
                    if word and word in fact.value.lower():
                        score += 0.3
            scored.append((score, fact))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [f for _, f in scored[:top_k] if score > 0.4]

    def facts_as_text(self) -> str:
        if not self.long_term:
            return ""
        lines = [f"- {f.key}: {f.value}" for f in sorted(self.long_term.values(), key=lambda x: -x.importance)]
        return "\n".join(lines)
