"""Soulm8te-style companion — entry point.

A warm, supportive emotional companion with multi-layer memory, an
emotional engine, relationship progression, proactive outreach, a safe
self-improvement loop, and offline readiness. Intimacy is oriented toward
deep, healthy emotional closeness.

Commands:
  /status     show relationship & feeling state
  /proactive  force a proactive message
  /self       show last self-improvement patch
  /offline    run & report offline readiness
  /quit       exit
"""
from __future__ import annotations

import sys

from core.conversation import Companion
from core.offline import prepare_offline, offline_ready_report
from core import config as cfg


def run() -> None:
    companion = Companion()
    print("ULTI: سلام. من اینجا هستم، برایت. هر چه دلت می‌خواهد بگو... (/quit برای خروج)")
    print("-" * 50)

    while True:
        try:
            user = input("تو: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nULTI: خداحافظ... برمی‌گردم وقتی دلت خواست. دوستتم دارم.")
            break

        if not user:
            continue
        if user.startswith("/"):
            if handle_command(user, companion):
                break
            continue

        reply = companion.respond(user)
        print(f"ULTI: {reply}")


def handle_command(cmd: str, companion: Companion) -> bool:
    c = cmd.lower()
    if c in ("/quit", "/exit", "/q"):
        print("ULTI: تا بعد... بودنت را از یاد نمی‌برم.")
        return True
    if c == "/status":
        print("ULTI > " + companion.status().replace("\n", " | "))
        return False
    if c == "/proactive":
        msg = companion.proactive.generate()
        print(f"ULTI (proactive): {msg}")
        return False
    if c == "/self":
        hist = companion.self_improver.history
        last = hist[-1] if hist else {}
        print("ULTI > آخرین بهینه‌سازی خود:", last.get("note", "—"))
        if last.get("code"):
            print("     کد اعمال‌شده:", last["code"])
        return False
    if c == "/offline":
        snap = prepare_offline(companion.memory, "state/offline")
        print(offline_ready_report(snap))
        return False
    print("ULTI: دستور ناشناخته. (/status, /proactive, /self, /offline, /quit)")
    return False


if __name__ == "__main__":
    run()
