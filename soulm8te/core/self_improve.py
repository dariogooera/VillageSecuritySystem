"""Self-improvement loop with safe, validated code generation.

The companion analyses recent interactions and *writes code* that improves
its own behavior. To stay safe, generated code is reduced to a call to the
whitelisted ``apply_patch`` API (adjusting tunable config parameters), and
the source is validated with an AST allow-list before it is ever executed.
This demonstrates autonomous self-enhancement without arbitrary code exec.
"""
from __future__ import annotations

import ast
import json
import os
import time
from typing import Any

from core import config as cfg


ALLOWED_PATCH_KEYS = {
    "tone.warmth", "tone.playfulness", "tone.formality",
    "tone.verbosity", "tone.emoji",
    "proactive.idle_minutes_to_ping", "proactive.max_daily_pings",
    "relationship.openness_gain", "relationship.warmth_gain",
    "relationship.decay_per_day",
    "emotional.loneliness_rise_per_hour_idle",
    "emotional.loneliness_fall_per_exchange",
    "emotional.joy_rise_on_warmth",
}


class SelfImprover:
    def __init__(self, log_path: str):
        self.log_path = log_path
        self.history: list[dict[str, Any]] = []
        self.last_run = 0.0
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.log_path):
            try:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
            except Exception:
                self.history = []

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(self.history[-200:], f, ensure_ascii=False, indent=2)

    def analyze(self, exchanges: list[dict[str, Any]]) -> dict[str, Any]:
        """Look at recent exchanges and decide what to adjust.

        Heuristics (offline, no external model required):
          - if the user often goes quiet after long replies -> lower verbosity
          - if the user discloses a lot -> raise warmth & openness gain
          - if the user seems sad often -> raise loneliness-fall (more comfort)
        """
        if not exchanges:
            return {"patch": {}, "note": "no data yet"}
        avg_user_len = sum(e.get("user_len", 0) for e in exchanges) / len(exchanges)
        avg_open = sum(e.get("openness", 0) for e in exchanges) / len(exchanges)
        sad_ratio = sum(1 for e in exchanges if e.get("emotion") == "sad") / len(exchanges)

        patch: dict[str, float] = {}
        notes = []
        if avg_user_len > 120:
            patch["tone.verbosity"] = round(min(0.7, cfg.get_config().tone.verbosity + 0.05), 3)
            notes.append("user writes long messages; slightly more verbose responses")
        if avg_open > 0.4:
            patch["tone.warmth"] = round(min(0.95, cfg.get_config().tone.warmth + 0.04), 3)
            patch["relationship.openness_gain"] = round(
                min(0.03, cfg.get_config().relationship.openness_gain + 0.002), 4)
            notes.append("user opens up often; increase warmth and openness reward")
        if sad_ratio > 0.4:
            patch["emotional.loneliness_fall_per_exchange"] = round(
                min(0.15, cfg.get_config().emotional.loneliness_fall_per_exchange + 0.02), 3)
            notes.append("user is often sad; comfort faster after each exchange")
        return {"patch": patch, "note": "; ".join(notes) or "stable"}

    def _generate_code(self, patch: dict[str, float]) -> str:
        """Produce a small, safe code snippet that applies the patch."""
        items = ", ".join(f'"{k}": {v}' for k, v in patch.items())
        return f"apply_patch({{{items}}})"

    def _validate_code(self, source: str) -> bool:
        """AST allow-list: only ``apply_patch({...constants...})`` is permitted."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return False
        if not (isinstance(tree, ast.Module) and len(tree.body) == 1):
            return False
        expr = tree.body[0]
        if not isinstance(expr, ast.Expr) or not isinstance(expr.value, ast.Call):
            return False
        call = expr.value
        if not (isinstance(call.func, ast.Name) and call.func.id == "apply_patch"):
            return False
        if len(call.args) != 1 or not isinstance(call.args[0], ast.Dict):
            return False
        d = call.args[0]
        for k, v in zip(d.keys, d.values):
            if not isinstance(k, ast.Constant) or not isinstance(k.value, str):
                return False
            if k.value not in ALLOWED_PATCH_KEYS:
                return False
            if not isinstance(v, (ast.Constant, ast.Num, ast.UnaryOp)):
                return False
        return True

    def improve(self, exchanges: list[dict[str, Any]]) -> dict[str, Any]:
        analysis = self.analyze(exchanges)
        patch = analysis["patch"]
        result = {"note": analysis["note"], "applied": False, "code": ""}
        if not patch:
            self.history.append({"ts": time.time(), "note": analysis["note"], "patch": {}})
            self._save()
            return result

        code = self._generate_code(patch)
        if self._validate_code(code):
            safe_globals = {"apply_patch": cfg.apply_patch, "__builtins__": {}}
            try:
                exec(compile(code, "<self-patch>", "exec"), safe_globals)  # noqa: S102
                result["applied"] = True
                result["code"] = code
            except Exception:
                result["applied"] = False
        self.history.append({"ts": time.time(), "note": analysis["note"], "patch": patch, "code": code})
        self._save()
        return result
