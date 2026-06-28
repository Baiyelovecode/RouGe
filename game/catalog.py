from __future__ import annotations

from collections.abc import Sequence

from game.data import RELICS, ROLE_RELIC_HOOKS, SKILLS, upgrade_skill
from game.models import Relic, Skill
from game.util import clear_screen


RARITY_NAMES = {
    "basic": "基础",
    "common": "普通",
    "uncommon": "罕见",
    "rare": "稀有",
}

CATEGORY_NAMES = {
    "attack": "攻击",
    "defense": "防御",
    "skill": "技能",
    "power": "能力",
    "weapon": "武器",
}

ROLE_NAMES = {
    "exile": "流亡者专属",
    "toxicist": "诡毒师专属",
    "burner": "燃尽者专属",
}


def card_catalog_entries() -> list[str]:
    rarity_order = {"basic": 0, "common": 1, "uncommon": 2, "rare": 3}
    cards = sorted(
        SKILLS.values(),
        key=lambda card: (rarity_order.get(card.rarity, 9), card.category, card.name),
    )
    return [_format_card(card) for card in cards]


def relic_catalog_entries() -> list[str]:
    relics = sorted(RELICS, key=lambda relic: (_relic_role(relic) != "通用", _relic_role(relic), relic.name))
    return [_format_relic(relic) for relic in relics]


def print_full_card_catalog() -> None:
    _print_full("卡牌图鉴", card_catalog_entries())


def print_full_relic_catalog() -> None:
    _print_full("遗物图鉴", relic_catalog_entries())


def browse_card_catalog() -> None:
    _browse("卡牌图鉴", card_catalog_entries(), page_size=6)


def browse_relic_catalog() -> None:
    _browse("遗物图鉴", relic_catalog_entries(), page_size=10)


def _format_card(card: Skill) -> str:
    first = upgrade_skill(card)
    second = upgrade_skill(first)
    rarity = RARITY_NAMES.get(card.rarity, card.rarity)
    category = CATEGORY_NAMES.get(card.category, card.category)
    return "\n".join([
        f"{card.name}  [{rarity} / {category}]  ID: {card.id}",
        f"  Lv.0  {card.cost}费 | {card.description}",
        f"  Lv.1  {first.cost}费 | {first.description}",
        f"  Lv.2  {second.cost}费 | {second.description}",
    ])


def _format_relic(relic: Relic) -> str:
    return f"{relic.name}  [{_relic_role(relic)}]\n  {relic.description}"


def _relic_role(relic: Relic) -> str:
    role_id = ROLE_RELIC_HOOKS.get(relic.hook)
    return ROLE_NAMES.get(role_id, "通用")


def _print_full(title: str, entries: Sequence[str]) -> None:
    print(f"\n{'=' * 64}\n{title} | 共 {len(entries)} 项\n{'=' * 64}")
    for index, entry in enumerate(entries, 1):
        print(f"\n{index}. {entry}")


def _browse(title: str, entries: Sequence[str], page_size: int) -> None:
    page = 0
    page_count = max(1, (len(entries) + page_size - 1) // page_size)
    while True:
        clear_screen()
        start = page * page_size
        current = entries[start:start + page_size]
        print(f"{title} | 共 {len(entries)} 项 | 第 {page + 1}/{page_count} 页")
        print("=" * 64)
        for offset, entry in enumerate(current, start + 1):
            print(f"\n{offset}. {entry}")
        print("\n[n] 下一页  [p] 上一页  [b] 返回")
        choice = input("> ").strip().lower()
        if choice in {"b", "back", "q", "quit"}:
            return
        if choice in {"n", "next"}:
            page = min(page + 1, page_count - 1)
        elif choice in {"p", "prev"}:
            page = max(page - 1, 0)
