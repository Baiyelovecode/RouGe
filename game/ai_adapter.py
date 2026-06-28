from __future__ import annotations

import contextlib
import io
import random
from typing import Any

from game.combat import Combat
from game.data import (
    SKILLS,
    act_floor_count,
    act_start_floor,
    create_player,
    enemy_group,
    normal_enemy,
    random_relic,
    random_relics,
    reward_skills,
    shop_skill_offers,
)
from game.models import Effect, Enemy, EnemyMove, Fighter, Player, Relic, Skill
from game.util import choose_many, clamp


NODE_NAMES = {
    "combat": "战斗",
    "elite": "精英",
    "event": "事件",
    "shop": "商店",
    "rest": "休息",
    "treasure": "宝箱",
    "training": "训练",
    "armory": "兵装",
    "boss": "Boss",
}


def _effect_to_dict(effect: Effect) -> dict[str, Any]:
    return {
        "kind": effect.kind,
        "value": effect.value,
        "target": effect.target,
        "times": effect.times,
    }


def _skill_to_dict(skill: Skill, index: int | None = None, preview: str | None = None) -> dict[str, Any]:
    data = {
        "id": skill.id,
        "name": skill.name,
        "cost": skill.cost,
        "category": skill.category,
        "rarity": skill.rarity,
        "description": skill.description,
        "upgrade_level": skill.upgrade_level,
        "effects": [_effect_to_dict(effect) for effect in skill.effects],
    }
    if index is not None:
        data["hand_index"] = index
    if preview:
        data["preview"] = preview
    return data


def _relic_to_dict(relic: Relic) -> dict[str, Any]:
    return {
        "id": relic.id,
        "name": relic.name,
        "description": relic.description,
        "hook": relic.hook,
        "value": relic.value,
    }


def _fighter_to_dict(fighter: Fighter) -> dict[str, Any]:
    return {
        "name": fighter.name,
        "hp": fighter.hp,
        "max_hp": fighter.max_hp,
        "block": fighter.block,
        "strength": fighter.strength,
        "dexterity": fighter.dexterity,
        "statuses": dict(fighter.statuses),
        "alive": fighter.alive,
    }


def _enemy_move_to_dict(move: EnemyMove | None) -> dict[str, Any] | None:
    if move is None:
        return None
    return {
        "name": move.name,
        "intent": move.intent,
        "effects": [_effect_to_dict(effect) for effect in move.effects],
    }


def _player_to_dict(player: Player) -> dict[str, Any]:
    data = _fighter_to_dict(player)
    data.update({
        "role_id": player.role_id,
        "energy": player.energy,
        "energy_max": player.energy_max,
        "gold": player.gold,
        "starter_bonus": player.starter_bonus,
        "turn_powers": dict(player.turn_powers),
        "skills": [_skill_to_dict(skill) for skill in player.skills],
        "relics": [_relic_to_dict(relic) for relic in player.relics],
        "potions": list(player.potions),
    })
    return data


class RogueGameAdapter:
    """Non-interactive adapter used by the Web UI and auto player."""

    def __init__(self, role_id: str = "exile", seed: int | None = None) -> None:
        if seed is not None:
            random.seed(seed)
        self.player: Player = create_player(role_id)
        self.act = 1
        self.floor = 1
        self.phase = "map"
        self.combat: Combat | None = None
        self.last_result: dict[str, Any] | None = None
        self.node_choices: list[str] = self._roll_node_choices()
        self.current_node: str | None = None
        self.pending_reward: list[Skill] = []
        self.pending_relic: Relic | None = None
        self.shop_state: dict[str, Any] | None = None
        self.choice_state: dict[str, Any] | None = None
        self.settlement: dict[str, Any] | None = None

    def choose_role(self, role_id: str) -> dict[str, Any]:
        if role_id not in {"exile", "toxicist", "burner"}:
            return self._error("unknown_role", f"未知角色: {role_id}")
        if self.phase == "combat":
            return self._error("invalid_phase", "战斗中不能切换角色")
        self.player = create_player(role_id)
        self.act = 1
        self.floor = 1
        self.phase = "map"
        self.combat = None
        self.last_result = None
        self.node_choices = self._roll_node_choices()
        self.current_node = None
        self.pending_reward = []
        self.pending_relic = None
        self.shop_state = None
        self.choice_state = None
        self.settlement = None
        return self._ok("choose_role", {"role_id": role_id, "player": _player_to_dict(self.player)})

    def start_combat(self, enemy_type: str = "normal", act: int | None = None) -> dict[str, Any]:
        if self.phase == "combat":
            return self._error("invalid_phase", "当前已经在战斗中")
        self.act = act or self.act
        self.settlement = None
        enemies = self._create_enemies(enemy_type)
        self.combat = Combat(self.player, enemies)
        self.phase = "combat"
        with self._suppress_stdout():
            self.combat._battle_start()
        for enemy in self.combat.enemies:
            enemy.select_next_move()
        self.combat._prepare_baiye_hand()
        self._start_player_turn()
        return self._ok("start_combat", {"enemy_type": enemy_type, "state": self.get_state()})

    def get_state(self) -> dict[str, Any]:
        state: dict[str, Any] = {
            "phase": self.phase,
            "act": self.act,
            "floor": self.floor,
            "floor_in_act": self._floor_in_act(),
            "node_choices": self._node_choices_to_dict(),
            "current_node": self.current_node,
            "pending_reward": [_skill_to_dict(skill, idx) for idx, skill in enumerate(self.pending_reward)],
            "pending_relic": _relic_to_dict(self.pending_relic) if self.pending_relic else None,
            "shop": self._shop_to_dict(),
            "choice": self._choice_to_dict(),
            "settlement": self.settlement,
            "player": _player_to_dict(self.player),
            "last_result": self.last_result,
        }
        if self.combat is not None:
            enemy = self.combat.ctx.enemy
            state["combat"] = {
                "turn": self.combat.ctx.turn,
                "enemy": {
                    **_fighter_to_dict(enemy),
                    "index": self.combat.target_index,
                    "active": True,
                    "intent": enemy.current_move.intent if enemy.current_move else "unknown",
                    "current_move": _enemy_move_to_dict(enemy.current_move),
                    "thorn_damage": enemy.thorn_damage,
                    "mechanics": dict(enemy.mechanics),
                },
                "enemies": [
                    {
                        **_fighter_to_dict(foe),
                        "index": idx,
                        "active": idx == self.combat.target_index,
                        "intent": foe.current_move.intent if foe.current_move else "unknown",
                        "current_move": _enemy_move_to_dict(foe.current_move),
                        "thorn_damage": foe.thorn_damage,
                        "mechanics": dict(foe.mechanics),
                    }
                    for idx, foe in enumerate(self.combat.enemies)
                ],
                "hand": [
                    _skill_to_dict(skill, idx, self.combat._skill_preview(skill))
                    for idx, skill in enumerate(self.combat.hand)
                ],
                "log": list(self.combat.ctx.log[-12:]),
                "turn_records": list(self.combat.turn_records[-20:]),
            }
        return state

    def get_legal_actions(self) -> list[dict[str, Any]]:
        if self.phase != "combat" or self.combat is None:
            return self._non_combat_actions()

        actions: list[dict[str, Any]] = []
        player = self.combat.ctx.player
        targets = [{"index": idx, "name": enemy.name} for idx, enemy in enumerate(self.combat.enemies) if enemy.alive]
        for idx, skill in enumerate(self.combat.hand):
            actions.append({
                "action": "play_card",
                "params": {"hand_index": idx},
                "legal": player.energy >= skill.cost,
                "reason": "ok" if player.energy >= skill.cost else "energy_not_enough",
                "card": _skill_to_dict(skill, idx, self.combat._skill_preview(skill)),
                "targets": targets if self.combat._skill_needs_enemy_target(skill) else [],
            })
        actions.append({"action": "end_turn", "params": {}, "legal": True, "reason": "ok"})
        return actions

    def execute_action(self, action: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        if action == "choose_role":
            return self.choose_role(str(params.get("role_id", "exile")))
        if action == "start_combat":
            return self.start_combat(str(params.get("enemy_type", "normal")), params.get("act"))
        if action == "choose_node":
            return self.choose_node(params)
        if action == "pick_reward":
            return self.pick_reward(params)
        if action == "skip_reward":
            return self.skip_reward()
        if action == "shop_buy":
            return self.shop_buy(params)
        if action == "shop_leave":
            return self.shop_leave()
        if action == "choice_select":
            return self.choice_select(params)
        if action == "select_target":
            return self.select_target(params)
        if action == "play_card":
            return self.play_card(params)
        if action == "end_turn":
            return self.end_turn()
        return self._error("unknown_action", f"未知动作: {action}")

    def choose_node(self, params: dict[str, Any]) -> dict[str, Any]:
        if self.phase != "map":
            return self._error("invalid_phase", "当前不在路线选择阶段")
        index = params.get("index")
        if not isinstance(index, int) or index < 0 or index >= len(self.node_choices):
            return self._error("invalid_node", "路线索引无效")
        node = self.node_choices[index]
        self.current_node = node
        if node in {"combat", "elite", "boss"}:
            enemy_type = "boss" if node == "boss" else "elite" if node == "elite" else "normal"
            return self.start_combat(enemy_type)
        if node == "treasure":
            relic = random_relic(self.player.relics, self.player.role_id)
            if relic:
                self.player.relics.append(relic)
            self.settlement = {
                "type": "treasure",
                "title": "宝箱结算",
                "relic": _relic_to_dict(relic) if relic else None,
                "lines": [f"获得遗物：{relic.name}" if relic else "没有新的遗物可获得。"],
            }
            self._advance_floor()
            return self._ok("treasure", {"relic": _relic_to_dict(relic) if relic else None, "state": self.get_state()})
        if node == "rest":
            self._prepare_rest()
        elif node == "training":
            self._prepare_training()
        elif node == "armory":
            self._prepare_armory()
        elif node == "shop":
            self._prepare_shop()
        elif node == "event":
            self._prepare_event()
        else:
            return self._error("unknown_node", node)
        return self._ok(node, {"state": self.get_state()})

    def select_target(self, params: dict[str, Any]) -> dict[str, Any]:
        if self.phase != "combat" or self.combat is None:
            return self._error("invalid_phase", "当前不在战斗中")
        index = params.get("target_index")
        if not isinstance(index, int):
            return self._error("invalid_target", "target_index 必须是数字")
        if not self.combat.set_target(index):
            return self._error("invalid_target", "目标无效或已经倒下")
        return self._ok("select_target", {"target_index": index, "state": self.get_state()})

    def play_card(self, params: dict[str, Any]) -> dict[str, Any]:
        if self.phase != "combat" or self.combat is None:
            return self._error("invalid_phase", "当前不在战斗中")
        if not self.combat.ctx.player.alive or not self.combat.has_living_enemies():
            return self._finish_if_needed()

        hand_index = params.get("hand_index")
        if hand_index is None and "card_id" in params:
            hand_index = self._find_hand_index_by_card_id(str(params["card_id"]))
        if not isinstance(hand_index, int):
            return self._error("invalid_params", "play_card 需要 hand_index 或 card_id")
        if hand_index < 0 or hand_index >= len(self.combat.hand):
            return self._error("invalid_card", f"手牌索引越界: {hand_index}")

        skill = self.combat.hand[hand_index]
        if self.combat.ctx.player.energy < skill.cost:
            return self._error("energy_not_enough", f"能量不足: {skill.name} 需要 {skill.cost}")
        target_index = params.get("target_index")
        if target_index is not None and not isinstance(target_index, int):
            return self._error("invalid_target", "target_index 必须是数字")
        if target_index is None:
            target_index = self.combat.target_index
        if self.combat._skill_needs_enemy_target(skill) and not self.combat.set_target(target_index):
            return self._error("invalid_target", "目标无效或已经倒下")

        before_log_len = len(self.combat.ctx.log)
        with self._suppress_stdout():
            used = self.combat._use_skill(skill, target_index)
        if used and skill in self.combat.hand:
            self.combat.hand.remove(skill)

        result = self._finish_if_needed()
        if result["status"] != "ok":
            return result
        if self._should_auto_end_turn():
            turn_result = self.end_turn()
            if turn_result["status"] != "success":
                return turn_result
            turn_result["result"]["auto_ended"] = True
            turn_result["result"]["played"] = _skill_to_dict(skill, hand_index)
            return turn_result
        return self._ok("play_card", {
            "played": _skill_to_dict(skill, hand_index),
            "logs": self.combat.ctx.log[before_log_len:],
            "state": self.get_state(),
        })

    def end_turn(self) -> dict[str, Any]:
        if self.phase != "combat" or self.combat is None:
            return self._error("invalid_phase", "当前不在战斗中")
        if not self.combat.ctx.player.alive or not self.combat.has_living_enemies():
            return self._finish_if_needed()

        before_log_len = len(self.combat.ctx.log)
        with self._suppress_stdout():
            self._finish_player_turn()
            if self.combat.has_living_enemies() and self.combat.ctx.player.alive:
                self.combat._enemy_turn()
            if self.combat.has_living_enemies() and self.combat.ctx.player.alive:
                self._start_player_turn()

        result = self._finish_if_needed()
        if result["status"] != "ok":
            return result
        return self._ok("end_turn", {
            "logs": self.combat.ctx.log[before_log_len:],
            "state": self.get_state(),
        })

    def pick_reward(self, params: dict[str, Any]) -> dict[str, Any]:
        if self.phase != "reward":
            return self._error("invalid_phase", "当前没有卡牌奖励")
        index = params.get("index")
        if not isinstance(index, int) or index < 0 or index >= len(self.pending_reward):
            return self._error("invalid_reward", "奖励索引无效")
        picked = self.pending_reward[index]
        self.player.skills.append(picked)
        if self.settlement is not None:
            self.settlement["picked"] = _skill_to_dict(picked)
        return self._finish_reward(picked)

    def skip_reward(self) -> dict[str, Any]:
        if self.phase != "reward":
            return self._error("invalid_phase", "当前没有卡牌奖励")
        if self.settlement is not None:
            self.settlement["picked"] = None
        return self._finish_reward(None)

    def shop_buy(self, params: dict[str, Any]) -> dict[str, Any]:
        if self.phase != "shop" or not self.shop_state:
            return self._error("invalid_phase", "当前不在商店")
        section = str(params.get("section", ""))
        index = params.get("index")
        if section == "heal":
            if not self._pay(35):
                return self._error("gold_not_enough", "金币不足")
            self.player.hp = clamp(self.player.hp + 20, 0, self.player.max_hp)
            return self._ok("shop_buy", {"bought": "heal", "state": self.get_state()})
        if section == "remove":
            if not isinstance(index, int) or index < 0 or index >= len(self.player.skills):
                return self._error("invalid_card", "移除卡牌索引无效")
            price = self.shop_state.get("remove_price", 60)
            if len(self.player.skills) <= 5:
                return self._error("deck_too_small", "卡组至少保留 5 张")
            if not self._pay(price):
                return self._error("gold_not_enough", "金币不足")
            removed = self.player.skills.pop(index)
            self.shop_state["remove_price"] = price + 30
            return self._ok("shop_remove", {"removed": _skill_to_dict(removed), "state": self.get_state()})
        if not isinstance(index, int):
            return self._error("invalid_shop_index", "商品索引无效")
        offers = self.shop_state.get(section)
        if not isinstance(offers, list) or index < 0 or index >= len(offers) or offers[index] is None:
            return self._error("invalid_shop_item", "商品不可购买")
        if section == "skills":
            card: Skill = offers[index]
            price = 70 if card.upgrade_level > 0 else 45
            if not self._pay(price):
                return self._error("gold_not_enough", "金币不足")
            self.player.skills.append(card)
            offers[index] = None
            return self._ok("shop_buy", {"bought": _skill_to_dict(card), "state": self.get_state()})
        if section == "relics":
            relic: Relic = offers[index]
            if not self._pay(90):
                return self._error("gold_not_enough", "金币不足")
            self.player.relics.append(relic)
            offers[index] = None
            return self._ok("shop_buy", {"bought": _relic_to_dict(relic), "state": self.get_state()})
        if section == "upgrades":
            card: Skill = offers[index]
            if not self._pay(60):
                return self._error("gold_not_enough", "金币不足")
            upgraded = self._upgrade_exact_skill(card)
            offers[index] = None
            return self._ok("shop_upgrade", {"upgraded": _skill_to_dict(upgraded) if upgraded else None, "state": self.get_state()})
        return self._error("unknown_shop_section", section)

    def shop_leave(self) -> dict[str, Any]:
        if self.phase != "shop":
            return self._error("invalid_phase", "当前不在商店")
        self.shop_state = None
        self._advance_floor()
        return self._ok("shop_leave", {"state": self.get_state()})

    def choice_select(self, params: dict[str, Any]) -> dict[str, Any]:
        if self.phase != "choice" or not self.choice_state:
            return self._error("invalid_phase", "当前没有可选事件")
        index = params.get("index")
        options = self.choice_state.get("options", [])
        if not isinstance(index, int) or index < 0 or index >= len(options):
            return self._error("invalid_choice", "选项索引无效")
        option = options[index]
        kind = option.get("kind")
        if kind == "heal":
            amount = max(1, self.player.max_hp * 30 // 100)
            self.player.hp = clamp(self.player.hp + amount, 0, self.player.max_hp)
        elif kind == "max_hp":
            self.player.max_hp += 8
            self.player.hp = clamp(self.player.hp + 8, 0, self.player.max_hp)
        elif kind == "upgrade":
            cards = option.get("cards", [])
            if cards:
                self._upgrade_exact_skill(cards[0])
            else:
                self.player.hp = self.player.max_hp
        elif kind == "upgrade_all":
            cards = option.get("cards", [])
            if cards:
                upgraded_names = []
                for card in cards:
                    upgraded = self._upgrade_exact_skill(card)
                    if upgraded:
                        upgraded_names.append(upgraded.name)
                self.settlement = {
                    "type": "training",
                    "title": "训练结算",
                    "lines": ["升级：" + " / ".join(upgraded_names)] if upgraded_names else ["没有可升级卡牌。"],
                }
            else:
                self.player.max_hp += 5
                self.player.hp = self.player.max_hp
                self.settlement = {
                    "type": "training",
                    "title": "训练结算",
                    "lines": ["所有卡牌都已满级，转为最大生命 +5 并完全恢复。"],
                }
        elif kind == "gain_card":
            card = option.get("card")
            if isinstance(card, Skill):
                self.player.skills.append(card)
        elif kind == "gold":
            self.player.gold += int(option.get("amount", 0))
        elif kind == "relic":
            relic = random_relic(self.player.relics, self.player.role_id)
            if relic:
                self.player.relics.append(relic)
        elif kind == "lose_hp_gain_card":
            self.player.hp = clamp(self.player.hp - int(option.get("hp", 0)), 1, self.player.max_hp)
            self.player.skills.append(random.choice(reward_skills(5)))
        self.choice_state = None
        self._advance_floor()
        return self._ok("choice_select", {"selected": option.get("label"), "state": self.get_state()})

    def _create_enemies(self, enemy_type: str) -> list[Enemy]:
        return enemy_group(enemy_type, self.act, self._floor_in_act())

    def _start_player_turn(self) -> None:
        assert self.combat is not None
        p = self.combat.ctx.player
        self.combat.ctx.turn += 1
        self.combat.ctx.attacks_this_turn = 0
        self.combat.ctx.blocks_this_turn = 0
        self.combat.player_burn_applied_this_turn = 0
        self.combat._tick_regeneration(p)
        debt = p.turn_powers.pop("energy_debt", 0)
        bonus_energy = p.turn_powers.pop("next_energy", 0)
        p.energy = max(0, p.energy_max + bonus_energy - debt)
        if self.combat.ctx.turn == 1:
            for relic in p.relics:
                if relic.hook == "first_turn_energy":
                    p.energy += relic.value
                    self.combat._log(f"{relic.name}：本回合能量 +{relic.value}。")
        self.combat._tick_poison(p)
        if self.combat.ctx.turn > 1 and not p.turn_powers.get("retain_block", 0):
            p.block = 0
        if p.turn_powers.get("ritual_block", 0):
            amount = p.turn_powers["ritual_block"] + p.dexterity
            p.block += amount
            self.combat._log(f"坚守：获得 {amount} 护甲。")
            self.combat._record(f"你获得 {amount} 护甲（坚守）")
        draw_count = 5 + p.turn_powers.pop("next_draw", 0)
        if self.combat.ctx.turn == 1:
            draw_count += sum(relic.value for relic in p.relics if relic.hook == "first_turn_draw")
        self.combat.hand = choose_many(self.combat._available_deck(), draw_count)

    def _finish_player_turn(self) -> None:
        assert self.combat is not None
        p = self.combat.ctx.player
        self.combat._apply_burner_end_powers()
        self.combat._apply_burner_passive()
        self.combat._tick_burn(p)
        self.combat._tick_bleed(p)
        self.combat._decay_statuses(p)

    def _should_auto_end_turn(self) -> bool:
        if self.phase != "combat" or self.combat is None:
            return False
        player = self.combat.ctx.player
        if not player.alive or not self.combat.has_living_enemies():
            return False
        return not any(skill.cost <= player.energy for skill in self.combat.hand)

    def _finish_if_needed(self) -> dict[str, Any]:
        assert self.combat is not None
        player = self.combat.ctx.player
        enemy = self.combat.ctx.enemy
        enemy_names = "、".join(enemy.name for enemy in self.combat.enemies)
        if self.combat.has_living_enemies() and player.alive:
            return {"status": "ok"}
        if player.alive:
            with self._suppress_stdout():
                self.combat._after_battle()
            gold = self._gold_with_relics(random.randint(12, 22) + self.act * 4)
            self.player.gold += gold
            self.pending_reward = reward_skills(4)
            if self.current_node in {"elite", "boss"}:
                self.pending_relic = random_relic(self.player.relics, self.player.role_id)
            self.settlement = {
                "type": "combat",
                "title": "战斗结算",
                "result": "won",
                "enemy": enemy_names,
                "node": self.current_node,
                "gold": gold,
                "player_hp": player.hp,
                "player_max_hp": player.max_hp,
                "records": list(self.combat.turn_records[-14:]),
                "logs": list(self.combat.ctx.log[-14:]),
                "reward_count": len(self.pending_reward),
                "relic": _relic_to_dict(self.pending_relic) if self.pending_relic else None,
            }
            self.phase = "reward"
            self.last_result = {"combat_result": "won", "enemy": enemy_names, "gold": gold}
            self.combat = None
            return self._ok("combat_finished", {"combat_result": "won", "state": self.get_state()})
        self.phase = "game_over"
        self.last_result = {"combat_result": "lost", "enemy": enemy_names}
        self.settlement = {
            "type": "combat",
            "title": "战斗结算",
            "result": "lost",
            "enemy": enemy_names,
            "node": self.current_node,
            "player_hp": player.hp,
            "player_max_hp": player.max_hp,
            "records": list(self.combat.turn_records[-14:]),
            "logs": list(self.combat.ctx.log[-14:]),
        }
        self.combat = None
        return self._ok("combat_finished", {"combat_result": "lost", "state": self.get_state()})

    def _finish_reward(self, picked: Skill | None) -> dict[str, Any]:
        relic = self.pending_relic
        if relic:
            self.player.relics.append(relic)
        self.pending_reward = []
        self.pending_relic = None
        self._advance_floor()
        return self._ok("pick_reward", {
            "picked": _skill_to_dict(picked) if picked else None,
            "relic": _relic_to_dict(relic) if relic else None,
            "state": self.get_state(),
        })

    def _non_combat_actions(self) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = [
            {"action": "choose_role", "params_schema": {"role_id": "exile|toxicist|burner"}},
        ]
        if self.phase == "map":
            actions.extend({
                "action": "choose_node",
                "params": {"index": idx},
                "legal": True,
                "reason": "ok",
                "node": node,
            } for idx, node in enumerate(self.node_choices))
        elif self.phase == "reward":
            actions.extend({
                "action": "pick_reward",
                "params": {"index": idx},
                "legal": True,
                "reason": "ok",
                "card": _skill_to_dict(skill, idx),
            } for idx, skill in enumerate(self.pending_reward))
            actions.append({"action": "skip_reward", "params": {}, "legal": True, "reason": "ok"})
        elif self.phase == "shop" and self.shop_state:
            actions.extend(self._shop_actions())
        elif self.phase == "choice" and self.choice_state:
            actions.extend({
                "action": "choice_select",
                "params": {"index": idx},
                "legal": True,
                "reason": "ok",
                "option": option,
            } for idx, option in enumerate(self.choice_state.get("options", [])))
        actions.append({"action": "start_combat", "params_schema": {"enemy_type": "normal|elite|boss"}})
        return actions

    def _roll_node_choices(self) -> list[str]:
        floor_in_act = self._floor_in_act()
        final_floor = act_floor_count(self.act)
        if floor_in_act == 1:
            return ["combat"]
        if floor_in_act == final_floor:
            return ["boss"]
        if floor_in_act == final_floor - 1:
            return ["rest", "shop", "training"]
        pool = ["combat", "combat", "combat", "event", "event", "treasure", "shop", "rest", "training", "armory"]
        if floor_in_act >= 3:
            pool.append("elite")
        return random.sample(pool, 4)

    def _floor_in_act(self) -> int:
        return self.floor - act_start_floor(self.act) + 1

    def _advance_floor(self) -> None:
        if self.player.role_id == "exile":
            self.player.strength = 0
            self.player.dexterity = 0
            old = self.player.starter_bonus
            self.player.starter_bonus = min(80, max(old + 1, (old * 118 + 99) // 100))
        if self._floor_in_act() == act_floor_count(self.act):
            self.act += 1
            if self.act > 4:
                self.phase = "victory"
                self.node_choices = []
                self.last_result = {"game_result": "won"}
                return
            self.floor = act_start_floor(self.act)
        else:
            self.floor += 1
        self.current_node = None
        self.phase = "map"
        self.node_choices = self._roll_node_choices()

    def _prepare_rest(self) -> None:
        self.phase = "choice"
        self.choice_state = {
            "title": "休息点",
            "options": [
                {"kind": "heal", "label": "恢复 30% 最大生命"},
                {"kind": "upgrade", "label": "随机升级 1 张卡", "cards": self._upgrade_offers()},
            ],
        }

    def _prepare_training(self) -> None:
        self.phase = "choice"
        self.choice_state = {
            "title": "训练场",
            "options": [
                {"kind": "max_hp", "label": "最大生命 +8，并恢复 8"},
                {"kind": "upgrade_all", "label": "随机 3 张卡全部升级", "cards": self._upgrade_offers()},
            ],
        }

    def _prepare_armory(self) -> None:
        weapons = random.sample([card for card in SKILLS.values() if card.category == "weapon"], 3)
        self.phase = "choice"
        self.choice_state = {
            "title": "兵装工坊",
            "options": [{"kind": "gain_card", "label": card.name, "card": card} for card in weapons]
                       + [{"kind": "gold", "label": "放弃兵装，获得 45 金币", "amount": 45}],
        }

    def _prepare_shop(self) -> None:
        upgrades = self._upgrade_offers()
        if not upgrades:
            self.player.gold += 100
        self.shop_state = {
            "skills": shop_skill_offers(),
            "relics": random_relics(self.player.relics, self.player.role_id, 4),
            "upgrades": upgrades,
            "remove_price": 60,
        }
        self.phase = "shop"

    def _prepare_event(self) -> None:
        self.phase = "choice"
        self.choice_state = {
            "title": "随机事件",
            "options": [
                {"kind": "relic", "label": "破损祠堂：获得 1 个遗物"},
                {"kind": "gold", "label": "旧钱袋：获得 50 金币", "amount": 50},
                {"kind": "lose_hp_gain_card", "label": "血字契约：失去 8 生命，获得 1 张牌", "hp": 8},
            ],
        }

    def _upgrade_offers(self) -> list[Skill]:
        candidates = [skill for skill in self.player.skills if skill.upgrade_level < 2]
        if len(candidates) <= 3:
            return candidates
        return random.sample(candidates, 3)

    def _upgrade_exact_skill(self, skill: Skill) -> Skill | None:
        for idx, owned in enumerate(self.player.skills):
            if owned is skill:
                upgraded = owned.upgraded_copy()
                self.player.skills[idx] = upgraded
                return upgraded
        return None

    def _gold_with_relics(self, amount: int) -> int:
        for relic in self.player.relics:
            if relic.id == "greedy_coin":
                amount = amount * 125 // 100
        return amount

    def _node_choices_to_dict(self) -> list[dict[str, Any]]:
        return [{"id": node, "name": NODE_NAMES.get(node, node), "index": idx} for idx, node in enumerate(self.node_choices)]

    def _shop_to_dict(self) -> dict[str, Any] | None:
        if not self.shop_state:
            return None
        return {
            "skills": [_skill_to_dict(card, idx) if card else None for idx, card in enumerate(self.shop_state["skills"])],
            "relics": [_relic_to_dict(relic) if relic else None for relic in self.shop_state["relics"]],
            "upgrades": [_skill_to_dict(card, idx) if card else None for idx, card in enumerate(self.shop_state["upgrades"])],
            "remove_price": self.shop_state.get("remove_price", 60),
        }

    def _choice_to_dict(self) -> dict[str, Any] | None:
        if not self.choice_state:
            return None
        options = []
        for idx, option in enumerate(self.choice_state.get("options", [])):
            data = {k: v for k, v in option.items() if k not in {"card", "cards"}}
            data["index"] = idx
            if isinstance(option.get("card"), Skill):
                data["card"] = _skill_to_dict(option["card"])
            if isinstance(option.get("cards"), list):
                data["cards"] = [_skill_to_dict(card, i) for i, card in enumerate(option["cards"])]
            options.append(data)
        return {"title": self.choice_state.get("title", "选择"), "options": options}

    def _shop_actions(self) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        assert self.shop_state is not None
        for idx, card in enumerate(self.shop_state["skills"]):
            if card:
                price = 70 if card.upgrade_level > 0 else 45
                actions.append({"action": "shop_buy", "params": {"section": "skills", "index": idx}, "legal": self.player.gold >= price, "price": price, "card": _skill_to_dict(card, idx)})
        for idx, relic in enumerate(self.shop_state["relics"]):
            if relic:
                actions.append({"action": "shop_buy", "params": {"section": "relics", "index": idx}, "legal": self.player.gold >= 90, "price": 90, "relic": _relic_to_dict(relic)})
        for idx, card in enumerate(self.shop_state["upgrades"]):
            if card:
                actions.append({"action": "shop_buy", "params": {"section": "upgrades", "index": idx}, "legal": self.player.gold >= 60, "price": 60, "card": _skill_to_dict(card, idx)})
        actions.append({"action": "shop_buy", "params": {"section": "heal"}, "legal": self.player.gold >= 35, "price": 35})
        actions.append({"action": "shop_leave", "params": {}, "legal": True, "reason": "ok"})
        return actions

    def _find_hand_index_by_card_id(self, card_id: str) -> int | None:
        assert self.combat is not None
        for idx, skill in enumerate(self.combat.hand):
            if skill.id == card_id:
                return idx
        return None

    def _pay(self, amount: int) -> bool:
        if self.player.gold < amount:
            return False
        self.player.gold -= amount
        return True

    @staticmethod
    @contextlib.contextmanager
    def _suppress_stdout():
        with contextlib.redirect_stdout(io.StringIO()):
            yield

    @staticmethod
    def _ok(action: str, result: dict[str, Any]) -> dict[str, Any]:
        return {"status": "success", "action": action, "result": result}

    @staticmethod
    def _error(code: str, message: str) -> dict[str, Any]:
        return {"status": "error", "error": {"code": code, "message": message}}
