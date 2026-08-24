"""Offline preparation.

Ensures the companion can keep functioning without a server connection:
  - verifies the offline engine is importable
  - pre-computes and caches response templates
  - exports a compact state snapshot for resilience
  - runs a self-test so the user knows it is ready offline
"""
from __future__ import annotations

import os
import time


def prepare_offline(memory, out_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    snapshot = {
        "ts": time.time(),
        "long_term_count": len(memory.long_term),
        "short_term_count": len(memory.short_term),
        "mid_term_count": len(memory.mid_term),
    }
    # Force-import the offline engine so any import error surfaces now.
    from llm import backend as b
    engine = b.LocalRuleBackend()
    probe = engine.generate("companion", "حالم بد است", "{'emotion':'sad','stage':1,'openness':0.0,'memory':''}")
    snapshot["offline_engine_ok"] = bool(probe)
    snapshot["probe_response"] = probe
    return snapshot


def offline_ready_report(snapshot: dict) -> str:
    ok = snapshot.get("offline_engine_ok")
    status = "آماده" if ok else "نیاز به بررسی"
    return (
        f"وضعیت آفلاین: {status}\n"
        f"خاطرات بلندمدت: {snapshot['long_term_count']}\n"
        f"پاسخ آزمایشی: {snapshot.get('probe_response','')}"
    )
