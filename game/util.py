from __future__ import annotations

import os
import random
from collections.abc import Sequence
from typing import TypeVar


T = TypeVar("T")


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def choose_many(items: Sequence[T], count: int) -> list[T]:
    if len(items) <= count:
        return list(items)
    return random.sample(list(items), count)


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def input_choice(prompt: str, valid: set[str]) -> str:
    while True:
        choice = input(prompt).strip().lower()
        if choice in {"q", "quit", "exit"}:
            raise KeyboardInterrupt
        if choice in valid:
            return choice
        print("无效输入，请重新选择。")


def status_text(statuses: dict[str, int]) -> str:
    names = {
        "vulnerable": "易伤",
        "weak": "虚弱",
        "poison": "中毒",
        "burn": "灼烧",
        "ritual_block": "坚守",
        "next_attack": "蓄势",
        "retain_block": "固守",
        "bleed": "流血",
        "fragile": "脆弱",
        "regeneration": "再生",
    }
    if not statuses:
        return "无"
    return ", ".join(f"{names.get(k, k)} {v}" for k, v in statuses.items())
