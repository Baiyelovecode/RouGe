from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


StatusMap = dict[str, int]


@dataclass(frozen=True)
class Effect:
    kind: str
    value: int
    target: str = "enemy"
    times: int = 1


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    cost: int
    category: str
    rarity: str
    description: str
    effects: tuple[Effect, ...]
    upgraded: bool = False
    upgrade_level: int = 0

    def upgraded_copy(self) -> "Skill":
        from game.data import upgrade_skill

        return upgrade_skill(self)


@dataclass
class Fighter:
    name: str
    max_hp: int
    hp: int
    block: int = 0
    strength: int = 0
    dexterity: int = 0
    statuses: StatusMap = field(default_factory=dict)

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def add_status(self, status: str, amount: int) -> None:
        if amount <= 0:
            return
        self.statuses[status] = self.statuses.get(status, 0) + amount

    def reduce_status(self, status: str, amount: int = 1) -> None:
        if status not in self.statuses:
            return
        self.statuses[status] -= amount
        if self.statuses[status] <= 0:
            del self.statuses[status]


@dataclass
class Player(Fighter):
    role_id: str = "exile"
    starter_bonus: int = 2
    energy_max: int = 3
    energy: int = 3
    gold: int = 99
    skills: list[Skill] = field(default_factory=list)
    relics: list["Relic"] = field(default_factory=list)
    potions: list[str] = field(default_factory=list)
    turn_powers: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class EnemyMove:
    name: str
    intent: str
    effects: tuple[Effect, ...]


@dataclass
class Enemy(Fighter):
    moves: list[EnemyMove] = field(default_factory=list)
    move_index: int = 0
    thorn_damage: int = 0
    current_move: EnemyMove | None = None
    boss_id: str = ""
    enraged: bool = False
    mechanics: dict[str, int] = field(default_factory=dict)

    def select_next_move(self) -> EnemyMove:
        if not self.moves:
            raise ValueError(f"{self.name} has no moves")
        self.current_move = self.moves[self.move_index % len(self.moves)]
        self.move_index += 1
        return self.current_move


RelicHook = Callable[["CombatContext"], None]


@dataclass(frozen=True)
class Relic:
    id: str
    name: str
    description: str
    hook: str
    value: int = 0


@dataclass
class CombatContext:
    player: Player
    enemy: Enemy
    turn: int
    log: list[str]
    attacks_this_turn: int = 0
    blocks_this_turn: int = 0
