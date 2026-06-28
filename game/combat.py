from __future__ import annotations

import math
import random
from collections import Counter

from game.models import CombatContext, Effect, Enemy, EnemyMove, Fighter, Player, Skill
from game.util import choose_many, clamp, clear_screen, input_choice, status_text


class Combat:
    def __init__(self, player: Player, enemy: Enemy | list[Enemy]) -> None:
        enemies = enemy if isinstance(enemy, list) else [enemy]
        if not enemies:
            raise ValueError("combat requires at least one enemy")
        self.enemies: list[Enemy] = enemies
        self.target_index = 0
        self.ctx = CombatContext(player=player, enemy=enemies[0], turn=0, log=[])
        self.hand: list[Skill] = []
        self.turn_records: list[str] = []
        self.clear_records_on_next_card = False
        self.player_burn_applied_this_turn = 0
        self.start_strength = player.strength
        self.start_dexterity = player.dexterity
        self.is_baiye = len(enemies) == 1 and enemies[0].boss_id == "baiye"
        self.baiye_shield_turns = 0
        self.baiye_heal_turns = 0
        self.baiye_heal_active = False
        self.baiye_heal_locked = False
        self.baiye_hand: list[Skill] = []
        self.exhausted_cards: Counter[tuple[str, int, int]] = Counter()
        self.defeated_enemy_ids: set[int] = set()

    def living_enemies(self) -> list[Enemy]:
        return [enemy for enemy in self.enemies if enemy.alive]

    def has_living_enemies(self) -> bool:
        return any(enemy.alive for enemy in self.enemies)

    def set_target(self, index: int) -> bool:
        if index < 0 or index >= len(self.enemies):
            return False
        if not self.enemies[index].alive:
            return False
        self.target_index = index
        self.ctx.enemy = self.enemies[index]
        return True

    def _retarget_if_needed(self) -> None:
        if self.ctx.enemy.alive:
            return
        for idx, enemy in enumerate(self.enemies):
            if enemy.alive:
                self.set_target(idx)
                return

    def run(self) -> bool:
        player = self.ctx.player
        enemy = self.ctx.enemy
        names = "、".join(enemy.name for enemy in self.enemies)
        print(f"\n遭遇：{names}")
        self._battle_start()
        for foe in self.enemies:
            foe.select_next_move()
        self._prepare_baiye_hand()

        while player.alive and self.has_living_enemies():
            self._player_turn()
            if not self.has_living_enemies() or not player.alive:
                break
            self._enemy_turn()

        if player.alive:
            print(f"\n你击败了 {names}。")
            self._after_battle()
            return True
        print("\n你倒在了塔中。本局结束。")
        return False

    def _battle_start(self) -> None:
        p = self.ctx.player
        p.block = 0
        p.statuses.clear()
        p.turn_powers.clear()
        self.exhausted_cards.clear()
        self.defeated_enemy_ids.clear()
        if p.role_id == "exile":
            bonus = p.starter_bonus
            for relic in p.relics:
                if relic.hook == "exile_start_bonus":
                    bonus += relic.value
            p.strength += bonus
            p.dexterity += bonus
            self._log(f"{p.name}：开战获得力量 +{bonus}，敏捷 +{bonus}。")
        for relic in p.relics:
            if relic.hook == "battle_start_block":
                p.block += relic.value
                self._log(f"{relic.name}：获得 {relic.value} 护甲。")
            elif relic.hook == "battle_start_strength":
                p.strength += relic.value
                self._log(f"{relic.name}：力量 +{relic.value}。")
            elif relic.hook == "battle_start_dexterity":
                p.dexterity += relic.value
                self._log(f"{relic.name}：敏捷 +{relic.value}。")
            elif relic.hook == "battle_start_poison":
                for enemy in self.enemies:
                    enemy.add_status("poison", relic.value)
                self._log(f"{relic.name}：所有敌人中毒 {relic.value}。")
            elif relic.hook == "battle_start_blood_stats":
                p.strength += relic.value
                p.dexterity += relic.value
                self._log(f"{relic.name}：力量 +{relic.value}，敏捷 +{relic.value}。")
            elif relic.hook == "battle_start_burn_block":
                p.block += relic.value + 2
                for enemy in self.enemies:
                    enemy.add_status("burn", relic.value)
                self._log(f"{relic.name}：获得 {relic.value + 2} 护甲，所有敌人灼烧 +{relic.value}。")
            elif relic.hook == "battle_start_burn":
                for enemy in self.enemies:
                    enemy.add_status("burn", relic.value)
                self._log(f"{relic.name}：所有敌人灼烧 +{relic.value}。")
            elif relic.hook == "battle_start_trinity":
                p.strength += relic.value
                p.dexterity += relic.value
                p.block += relic.value * 6
                self._log(f"{relic.name}：力量/敏捷 +{relic.value}，护甲 +{relic.value * 6}。")
            elif relic.hook == "battle_start_regeneration":
                p.add_status("regeneration", relic.value)
                self._log(f"{relic.name}：获得 {relic.value} 层再生。")
        for enemy in self.enemies:
            shell_guard = enemy.mechanics.get("shell_guard", 0)
            if shell_guard > 0:
                enemy.block += shell_guard
                self._log(f"{enemy.name} 甲壳护卫：开战获得 {shell_guard} 护甲。")
                self._record(f"{enemy.name} 护甲 +{shell_guard}（甲壳护卫）")
            thorn = enemy.mechanics.get("thorn", 0)
            if thorn > 0:
                enemy.thorn_damage = max(enemy.thorn_damage, thorn)
                self._log(f"{enemy.name} 尖刺外壳：攻击牌会反伤 {enemy.thorn_damage}。")

    def _player_turn(self) -> None:
        p = self.ctx.player
        self.ctx.turn += 1
        self.ctx.attacks_this_turn = 0
        self.ctx.blocks_this_turn = 0
        self.player_burn_applied_this_turn = 0
        self._tick_regeneration(p)
        debt = p.turn_powers.pop("energy_debt", 0)
        bonus_energy = p.turn_powers.pop("next_energy", 0)
        p.energy = max(0, p.energy_max + bonus_energy - debt)
        if debt:
            self._log(f"能量透支：本回合能量 -{debt}。")
        if bonus_energy:
            self._log(f"储能释放：本回合能量 +{bonus_energy}。")
        if self.ctx.turn == 1:
            for relic in p.relics:
                if relic.hook == "first_turn_energy":
                    p.energy += relic.value
                    self._log(f"{relic.name}：本回合能量 +{relic.value}。")

        self._tick_poison(p)
        if self.ctx.turn > 1 and not p.turn_powers.get("retain_block", 0):
            p.block = 0
        if p.turn_powers.get("ritual_block", 0):
            amount = p.turn_powers["ritual_block"] + p.dexterity
            p.block += amount
            self._log(f"坚守：获得 {amount} 护甲。")
            self._record(f"你获得 {amount} 护甲（坚守）")
        draw_count = 5 + p.turn_powers.pop("next_draw", 0)
        if self.ctx.turn == 1:
            draw_count += sum(relic.value for relic in p.relics if relic.hook == "first_turn_draw")
        self.hand = choose_many(self._available_deck(), draw_count)

        while p.alive and self.has_living_enemies():
            self._retarget_if_needed()
            if not self.hand:
                self._log("手牌已用完，自动结束回合。")
                self._record("手牌已用完，自动结束回合")
                break
            if self._should_auto_end_turn():
                self._log("能量为 0 且没有可使用技能，自动结束回合。")
                break
            self._print_state()
            valid = {str(i) for i in range(1, len(self.hand) + 1)} | {"end", "log", "skills", "relics"}
            choice = input_choice("> ", valid)
            if choice == "end":
                break
            if choice == "log":
                self._print_log()
                continue
            if choice == "skills":
                self._print_skills()
                continue
            if choice == "relics":
                self._print_relics()
                continue
            selected = self.hand[int(choice) - 1]
            if self._use_skill(selected):
                self.hand.remove(selected)

        self._apply_burner_end_powers()
        self._apply_burner_passive()
        self._tick_burn(p)
        self._tick_bleed(p)
        self._decay_statuses(p)

    def _enemy_turn(self) -> None:
        player = self.ctx.player
        self.turn_records.clear()
        if self.is_baiye:
            self._baiye_turn()
            return
        for idx, enemy in enumerate(list(self.enemies)):
            if not enemy.alive:
                continue
            self.set_target(idx)
            self._tick_regeneration(enemy)
            self._tick_poison(enemy)
            if not enemy.alive:
                continue
            enemy.block = 0
            rally_block = enemy.mechanics.get("rally_block", 0)
            if rally_block > 0:
                for ally in self.living_enemies():
                    self._gain_block(ally, rally_block, add_dexterity=False)
                self._log(f"{enemy.name} 号令：全体敌人获得 {rally_block} 护甲。")
                self._record(f"{enemy.name} 号令：全体敌人护甲 +{rally_block}")
            move = enemy.current_move or enemy.select_next_move()
            self._log(f"{enemy.name} 使用 {move.name}。")
            self._record(f"{enemy.name} 使用 {move.name}")
            for effect in move.effects:
                self._apply_effect(enemy, player, effect)
                if not player.alive:
                    return
            self._tick_burn(enemy)
            self._tick_bleed(enemy)
            self._decay_statuses(enemy)
            enemy.select_next_move()
        self.clear_records_on_next_card = True

    def _baiye_turn(self) -> None:
        enemy = self.ctx.enemy
        player = self.ctx.player
        self._advance_baiye_shield()
        self._tick_regeneration(enemy)
        self._tick_poison(enemy)
        if not enemy.alive or not player.alive:
            return
        self._advance_baiye_healing()
        cards = self.baiye_hand or self._baiye_cards()
        play_count = random.randint(1, 3)
        played = random.sample(cards, play_count)
        self._log(f"Baiye 获得 3 张专属兵装，打出 {play_count} 张。")
        for card in played:
            self._log(f"Baiye 使用 {card.name}：{card.description}")
            self._record(f"Baiye 使用 {card.name} | {card.description}")
            attacked = False
            for effect in card.effects:
                if effect.kind == "baiye_shield":
                    enemy.block += effect.value
                    self.baiye_shield_turns = 3
                    self._log(f"Baiye 获得 {effect.value} 护甲，3 回合后释放剩余护甲。")
                    self._record(f"Baiye 护甲 +{effect.value}，反击倒计时 3")
                    continue
                self._apply_effect(enemy, player, effect, card)
                attacked = attacked or effect.kind in {"damage", "weapon_damage", "lifesteal_damage"}
                if not player.alive:
                    return
            if attacked and enemy.hp < 499:
                player.add_status("burn", max(0, enemy.strength))
                player.add_status("poison", max(0, enemy.dexterity))
                self._log(f"Baiye 残血追猎：施加 {enemy.strength} 灼烧与 {enemy.dexterity} 中毒。")
                self._record(f"你获得灼烧 {enemy.strength} / 中毒 {enemy.dexterity}")
        self._tick_burn(enemy)
        self._tick_bleed(enemy)
        self._decay_statuses(enemy)
        self._prepare_baiye_hand()
        self.clear_records_on_next_card = True

    def _prepare_baiye_hand(self) -> None:
        if not self.is_baiye:
            return
        self.baiye_hand = self._baiye_cards()
        names = "；".join(f"{card.name} Lv.{card.upgrade_level}: {card.description}" for card in self.baiye_hand)
        self.ctx.enemy.current_move = EnemyMove("白夜兵装", f"下回合随机打出 1-3 张。候选：{names}", ())

    def _baiye_cards(self) -> list[Skill]:
        templates = [
            ("baiye_slash", "白夜斩", "attack", 44, 0, "damage"),
            ("baiye_dual", "双月连斩", "attack", 26, 2, "damage"),
            ("baiye_crush", "压迫力场", "attack", 34, 0, "crush"),
            ("baiye_plaguefire", "毒火刻印", "skill", 22, 0, "plaguefire"),
            ("baiye_temper", "白夜淬刃", "power", 5, 0, "temper"),
            ("baiye_aegis", "白夜壁垒", "power", 200, 0, "aegis"),
        ]
        picks = random.sample(templates, 3)
        return [self._build_baiye_card(*template, level=random.randint(0, 2)) for template in picks]

    def _build_baiye_card(self, id_: str, name: str, category: str, value: int, times: int, kind: str, level: int) -> Skill:
        suffix = "+" * level
        if kind == "damage":
            damage = value + level * 12
            repeat = times or 1
            desc = f"基础伤害 {damage}" + (f" x{repeat}" if repeat > 1 else "") + "。先加 Baiye 力量，再算玩家护甲。"
            return Skill(id_, name + suffix, 0, category, "boss", desc, (Effect("damage", damage, times=repeat),), level > 0, level)
        if kind == "crush":
            damage = value + level * 10
            debuff = 2 + level
            desc = f"基础伤害 {damage}，并施加虚弱 {debuff}、易伤 {debuff}。"
            return Skill(id_, name + suffix, 0, category, "boss", desc, (
                Effect("damage", damage),
                Effect("weak", debuff),
                Effect("vulnerable", debuff),
            ), level > 0, level)
        if kind == "plaguefire":
            damage = value + level * 8
            status = 18 + level * 8
            desc = f"基础伤害 {damage}，并施加灼烧 {status}、中毒 {status}。"
            return Skill(id_, name + suffix, 0, category, "boss", desc, (
                Effect("damage", damage),
                Effect("burn", status),
                Effect("poison", status),
            ), level > 0, level)
        if kind == "temper":
            stat = value + level * 2
            block = 80 + level * 40
            desc = f"Baiye 力量 +{stat}、敏捷 +{stat}，并获得 {block} 护甲。"
            return Skill(id_, name + suffix, 0, category, "boss", desc, (
                Effect("strength", stat, "self"),
                Effect("dexterity", stat, "self"),
                Effect("block", block, "self"),
            ), level > 0, level)
        shield = value + level * 50
        desc = f"获得 {shield} 护甲。3 回合后对玩家造成 Baiye 剩余护甲等量伤害。"
        return Skill(id_, name + suffix, 0, category, "boss", desc, (Effect("baiye_shield", shield, "self"),), level > 0, level)

    def _advance_baiye_shield(self) -> None:
        if self.baiye_shield_turns <= 0:
            self.ctx.enemy.block = 0
            return
        self.baiye_shield_turns -= 1
        self._record(f"Baiye 护甲反击倒计时 {self.baiye_shield_turns}")
        if self.baiye_shield_turns == 0:
            damage = self.ctx.enemy.block
            self.ctx.enemy.block = 0
            if damage > 0:
                self._deal_fixed_damage(self.ctx.enemy, self.ctx.player, damage, "白夜壁垒反击")

    def _advance_baiye_healing(self) -> None:
        enemy = self.ctx.enemy
        if self.baiye_heal_locked and enemy.hp < 999:
            self.baiye_heal_locked = False
        if enemy.hp < 999 and not self.baiye_heal_locked:
            self.baiye_heal_active = True
        if not self.baiye_heal_active:
            return
        self.baiye_heal_turns += 1
        if self.baiye_heal_turns < 2:
            return
        self.baiye_heal_turns = 0
        amount = math.ceil(enemy.max_hp * 0.2)
        healed = min(amount, enemy.max_hp - enemy.hp)
        enemy.hp += healed
        self._log(f"Baiye 夜返：回复 {healed} 生命。")
        self._record(f"Baiye 回复 {healed} 生命（夜返）")
        if enemy.hp > 1500:
            self.baiye_heal_active = False
            self.baiye_heal_locked = True

    def _use_skill(self, skill: Skill, target_index: int | None = None) -> bool:
        p = self.ctx.player
        if target_index is not None and self._skill_needs_enemy_target(skill):
            if not self.set_target(target_index):
                print("目标无效。")
                return False
        self._retarget_if_needed()
        enemy = self.ctx.enemy
        if p.energy < skill.cost:
            print("能量不足。")
            return False
        if self.clear_records_on_next_card:
            self.turn_records.clear()
            self.clear_records_on_next_card = False
        p.energy -= skill.cost
        self._log(f"你使用 {skill.name}。")
        self._record(f"你使用 {skill.name}")
        original_target = enemy
        enemy_hp_before = enemy.hp
        block_before = p.block
        is_group_card = self._is_group_skill(skill)
        for effect in skill.effects:
            self._apply_effect(p, enemy, effect, skill)
            if not enemy.alive:
                self._retarget_if_needed()
                break
        if is_group_card:
            group_block = sum(relic.value for relic in p.relics if relic.hook == "group_card_block")
            if group_block > 0:
                self._gain_block(p, group_block, add_dexterity=False)
                self._record(f"群体牌触发遗物：护甲 +{group_block}")
        burn_on_card = p.turn_powers.get("burn_on_card", 0)
        if burn_on_card and enemy.alive:
            amount = skill.cost * burn_on_card + p.turn_powers.get("burn_on_card_flat", 2)
            enemy.add_status("burn", amount)
            self.player_burn_applied_this_turn += amount
            self._log(f"余烬引擎：{enemy.name} 灼烧 +{amount}。")
            self._record(f"余烬引擎：{enemy.name} 灼烧 +{amount}")
        self._apply_toxicist_passive(skill, enemy_hp_before - original_target.hp, max(0, p.block - block_before), original_target)
        return True

    @staticmethod
    def _skill_needs_enemy_target(skill: Skill) -> bool:
        enemy_effects = {
            "damage", "weapon_damage", "lifesteal_damage", "poison_burst", "vulnerable", "weak",
            "poison", "burn", "bleed", "fragile", "burn_echo", "draw_if_weak", "damage_per_debuff",
            "consume_debuffs", "damage_from_burn", "strength_if_burning", "strength_finisher",
            "exhaust_hand_damage", "exhaust_hand_poison", "exhaust_hand_burn", "poison_if_poisoned",
            "damage_from_block",
        }
        return any(effect.target != "self" and effect.kind in enemy_effects for effect in skill.effects)

    @staticmethod
    def _is_group_skill(skill: Skill) -> bool:
        group_effects = {
            "damage_all", "damage_all_per_enemy", "poison_all", "burn_all", "weak_all",
            "vulnerable_all", "poison_burst_all", "damage_from_burn_all",
        }
        return any(effect.kind in group_effects for effect in skill.effects)

    def _should_auto_end_turn(self) -> bool:
        p = self.ctx.player
        return p.energy == 0 and not any(skill.cost <= p.energy for skill in self.hand)

    def _apply_effect(self, source: Fighter, target: Fighter, effect: Effect, skill: Skill | None = None) -> None:
        actual_target = source if effect.target == "self" else target
        # This effect uses ``times`` as a strength multiplier, not as a repeat count.
        if effect.kind == "block_with_strength":
            strength = max(0, source.strength)
            amount = effect.value + strength * effect.times
            self._gain_block(actual_target, amount, add_dexterity=False)
            self._log(
                f"铁壁吐息公式：{effect.value} + 力量 {strength} x{effect.times} = {amount} 护甲。"
            )
            return
        if effect.kind == "damage_all_per_enemy":
            base = effect.value + len(self.living_enemies()) * effect.times + self._group_damage_bonus(source)
            self._log(f"群体伤害公式：{effect.value} + 存活敌人 {len(self.living_enemies())} x {effect.times} = {base}。")
            for enemy in list(self.living_enemies()):
                self._deal_damage(source, enemy, base, skill)
            return
        if effect.kind == "block_per_enemy":
            amount = effect.value + len(self.living_enemies()) * effect.times
            self._log(f"群体护甲公式：{effect.value} + 存活敌人 {len(self.living_enemies())} x {effect.times} = {amount}。")
            self._gain_block(actual_target, amount)
            return
        for _ in range(effect.times):
            if effect.kind == "damage":
                self._deal_damage(source, actual_target, effect.value, skill)
            elif effect.kind == "damage_all":
                base = effect.value + self._group_damage_bonus(source)
                for enemy in list(self.living_enemies()):
                    self._deal_damage(source, enemy, base, skill)
            elif effect.kind == "weapon_damage":
                self._deal_weapon_damage(source, actual_target, effect.value, skill)
            elif effect.kind == "lifesteal_damage":
                dealt = self._deal_damage(source, actual_target, effect.value, skill)
                if isinstance(source, Player) and dealt > 0:
                    heal = max(1, dealt // 2 + max(0, source.strength) + max(0, source.dexterity))
                    for relic in source.relics:
                        if relic.hook == "lifesteal_bonus":
                            heal += relic.value
                    source.hp = clamp(source.hp + heal, 0, source.max_hp)
                    self._log(f"{source.name} 吸血回复 {heal} 生命。")
                    self._record(f"{source.name} 回复 {heal} 生命（吸血）")
            elif effect.kind == "poison_burst":
                self._apply_poison_burst(source, actual_target, effect.value)
            elif effect.kind == "block":
                self._gain_block(actual_target, effect.value)
            elif effect.kind == "damage_from_block":
                self._deal_fixed_damage(source, actual_target, math.ceil(source.block * effect.value / 100), "护甲联动")
            elif effect.kind == "block_from_strength":
                self._gain_block(actual_target, max(0, source.strength * effect.value), add_dexterity=False)
                self._record(f"铁壁吐息获得 {amount} 护甲")
            elif effect.kind == "block_from_enemy_poison":
                amount = math.ceil(target.statuses.get("poison", 0) * effect.value / 100)
                if isinstance(actual_target, Player):
                    amount += sum(r.value for r in actual_target.relics if r.hook == "poison_block_bonus")
                self._gain_block(actual_target, amount, add_dexterity=False)
            elif effect.kind == "burn_echo":
                existing = actual_target.statuses.get("burn", 0)
                amount = math.ceil(existing * effect.value / 100)
                actual_target.add_status("burn", amount)
                self._log(f"灼烧联动：{actual_target.name} 额外获得灼烧 {amount}。")
                self._record(f"{actual_target.name} 灼烧联动 +{amount}")
                if isinstance(source, Player) and isinstance(actual_target, Enemy):
                    self.player_burn_applied_this_turn += amount
            elif effect.kind in {"vulnerable", "weak", "poison", "burn", "bleed", "fragile", "regeneration"}:
                actual_target.add_status(effect.kind, effect.value)
                self._log(f"{actual_target.name} 获得 {self._status_name(effect.kind)} {effect.value}。")
                self._record(f"{actual_target.name} 获得 {self._status_name(effect.kind)} {effect.value}")
                if effect.kind == "burn" and isinstance(source, Player) and isinstance(actual_target, Enemy):
                    self.player_burn_applied_this_turn += effect.value
            elif effect.kind in {"poison_all", "burn_all", "weak_all", "vulnerable_all"}:
                status = {
                    "poison_all": "poison",
                    "burn_all": "burn",
                    "weak_all": "weak",
                    "vulnerable_all": "vulnerable",
                }[effect.kind]
                for enemy in self.living_enemies():
                    enemy.add_status(status, effect.value)
                    self._log(f"{enemy.name} 获得 {self._status_name(status)} {effect.value}。")
                    self._record(f"{enemy.name} 获得 {self._status_name(status)} {effect.value}")
                    if status == "burn" and isinstance(source, Player):
                        self.player_burn_applied_this_turn += effect.value
            elif effect.kind == "poison_burst_all":
                for enemy in list(self.living_enemies()):
                    self._apply_poison_burst(source, enemy, effect.value)
            elif effect.kind == "damage_from_burn_all":
                for enemy in list(self.living_enemies()):
                    amount = math.ceil(enemy.statuses.get("burn", 0) * effect.value / 100)
                    self._deal_fixed_damage(source, enemy, amount, "全体熔火追击")
            elif effect.kind == "energy" and isinstance(actual_target, Player):
                actual_target.energy += effect.value
                self._log(f"{actual_target.name} 获得 {effect.value} 点能量。")
                self._record(f"{actual_target.name} 能量 +{effect.value}")
            elif effect.kind in {"energy_debt", "next_energy", "next_draw"} and isinstance(actual_target, Player):
                actual_target.turn_powers[effect.kind] = actual_target.turn_powers.get(effect.kind, 0) + effect.value
                self._log(f"{actual_target.name} 获得 {self._status_name(effect.kind)} {effect.value}。")
            elif effect.kind == "draw" and isinstance(actual_target, Player):
                self._draw_cards(effect.value)
            elif effect.kind == "draw_if_weak" and isinstance(source, Player):
                if target.statuses.get("weak", 0) > 0:
                    self._draw_cards(effect.value)
                    self._log(f"乘隙追击：目标处于虚弱，额外抽 {effect.value} 张牌。")
            elif effect.kind == "damage_per_debuff":
                layers = sum(target.statuses.get(status, 0) for status in ("weak", "vulnerable", "fragile"))
                if layers > 0:
                    self._deal_fixed_damage(source, target, layers * effect.value, "负面状态联动")
                    self._log(f"负面状态联动：{layers} 层 x {effect.value}。")
            elif effect.kind == "consume_debuffs" and isinstance(source, Player):
                consumed = sum(target.statuses.pop(status, 0) for status in ("weak", "vulnerable", "fragile"))
                if consumed > 0:
                    source.energy += consumed
                    self._gain_block(source, consumed * effect.value, add_dexterity=False)
                    self._log(f"状态收割：移除 {consumed} 层负面状态，能量 +{consumed}。")
                else:
                    self._log("状态收割：目标没有可收割的负面状态。")
            elif effect.kind == "damage_from_burn":
                amount = math.ceil(target.statuses.get("burn", 0) * effect.value / 100)
                self._deal_fixed_damage(source, target, amount, "熔火追击")
            elif effect.kind == "strength_if_burning" and isinstance(source, Player):
                if target.statuses.get("burn", 0) > 0:
                    source.strength += effect.value
                    self._log(f"灰烬淬体：力量 +{effect.value}。")
                    self._record(f"{source.name} 力量 +{effect.value}（灰烬淬体）")
            elif effect.kind == "strength_finisher":
                base = 36 if skill and skill.upgrade_level >= 1 else 24
                threshold = 20 if skill and skill.upgrade_level >= 1 else 25
                amount = base + max(0, source.strength) * effect.value
                if target.statuses.get("burn", 0) >= threshold:
                    amount = math.floor(amount * 1.5)
                self._deal_fixed_damage(source, target, amount, "日轮坍缩")
            elif effect.kind in {"burn_tick_strength", "end_burn_from_strength", "next_burn_multiplier",
                                 "burn_rekindle", "burn_on_card"} and isinstance(actual_target, Player):
                actual_target.turn_powers[effect.kind] = actual_target.turn_powers.get(effect.kind, 0) + effect.value
                if effect.kind == "burn_on_card":
                    actual_target.turn_powers["burn_on_card_flat"] = max(
                        actual_target.turn_powers.get("burn_on_card_flat", 0),
                        3 if skill and skill.upgrade_level >= 1 else 2,
                    )
                self._log(f"{actual_target.name} 获得 {self._status_name(effect.kind)} {effect.value}。")
            elif effect.kind == "exhaust_self" and isinstance(source, Player) and skill is not None:
                self._exhaust_card(skill)
            elif effect.kind in {"exhaust_hand_damage", "exhaust_hand_poison", "exhaust_hand_burn"} and isinstance(source, Player):
                exhausted = self._exhaust_hand(skill, include_self=effect.kind == "exhaust_hand_damage")
                if effect.kind == "exhaust_hand_damage":
                    attribute_bonus = max(0, source.strength) + max(0, source.dexterity)
                    total_damage = exhausted * effect.value + attribute_bonus
                    self._deal_fixed_damage(source, target, total_damage, "孤注一掷")
                    self._log(
                        f"孤注一掷公式：{exhausted} x {effect.value} + "
                        f"力量 {max(0, source.strength)} + 敏捷 {max(0, source.dexterity)} = {total_damage}。"
                    )
                elif effect.kind == "exhaust_hand_poison":
                    target.add_status("poison", exhausted * effect.value)
                    self._log(f"毒囊清仓：施加 {exhausted * effect.value} 层中毒。")
                else:
                    burn = exhausted * effect.value
                    target.add_status("burn", burn)
                    self.player_burn_applied_this_turn += burn
                    block_per_card = 2 if skill and skill.upgrade_level >= 1 else 1
                    self._gain_block(source, exhausted * block_per_card, add_dexterity=False)
                    self._log(f"余烬回收：施加 {burn} 层灼烧。")
            elif effect.kind == "poison_if_poisoned":
                if actual_target.statuses.get("poison", 0) > 0:
                    actual_target.add_status("poison", effect.value)
                    self._log(f"{actual_target.name} 已中毒，额外获得中毒 {effect.value}。")
                    self._record(f"{actual_target.name} 额外获得中毒 {effect.value}")
            elif effect.kind == "strength":
                actual_target.strength += effect.value
                self._log(f"{actual_target.name} 力量 +{effect.value}。")
                self._record(f"{actual_target.name} 力量 +{effect.value}")
            elif effect.kind == "dexterity":
                actual_target.dexterity += effect.value
                self._log(f"{actual_target.name} 敏捷 +{effect.value}。")
                self._record(f"{actual_target.name} 敏捷 +{effect.value}")
            elif effect.kind in {"ritual_block", "next_attack", "retain_block"} and isinstance(actual_target, Player):
                actual_target.turn_powers[effect.kind] = actual_target.turn_powers.get(effect.kind, 0) + effect.value
                self._log(f"{actual_target.name} 获得 {self._status_name(effect.kind)} {effect.value}。")
                self._record(f"{actual_target.name} 获得 {self._status_name(effect.kind)} {effect.value}")

    def _deal_damage(self, source: Fighter, target: Fighter, base: int, skill: Skill | None) -> int:
        damage = base + source.strength
        formula_parts = [f"基础 {base}", f"力量 {source.strength}"]
        if isinstance(source, Enemy):
            pack_bonus = source.mechanics.get("pack_hunter", 0)
            if pack_bonus > 0 and len(self.living_enemies()) > 1:
                damage += pack_bonus
                formula_parts.append(f"群猎 {pack_bonus}")
                self._log(f"{source.name} 群猎：伤害 +{pack_bonus}。")
        if isinstance(source, Player):
            for relic in source.relics:
                if relic.hook == "attack_bonus":
                    damage += relic.value
                    formula_parts.append(f"{relic.name} {relic.value}")
            bonus = source.turn_powers.pop("next_attack", 0)
            if bonus:
                damage += bonus
                formula_parts.append(f"蓄势 {bonus}")
                self._log(f"蓄势触发：伤害 +{bonus}。")
            self.ctx.attacks_this_turn += 1
        if source.statuses.get("weak", 0):
            damage = math.floor(damage * 0.75)
            formula_parts.append("虚弱 x0.75")
        if target.statuses.get("vulnerable", 0):
            damage = math.floor(damage * 1.5)
            formula_parts.append("易伤 x1.5")
        damage = max(0, damage)
        was_alive = isinstance(target, Enemy) and target.alive
        absorbed = min(target.block, damage)
        target.block -= absorbed
        hp_damage = damage - absorbed
        target.hp = clamp(target.hp - hp_damage, 0, target.max_hp)
        self._on_enemy_hp_loss(target, hp_damage)
        if was_alive and isinstance(target, Enemy) and not target.alive:
            self._handle_enemy_defeat(target, source, skill)
        self._log(f"{source.name} 对 {target.name} 造成 {hp_damage} 伤害。")
        self._record(
            f"{source.name} -> {target.name}：{' + '.join(formula_parts)} => {damage}；"
            f"护甲抵消 {absorbed}；生命 -{hp_damage}"
        )
        if hp_damage > 0:
            self._record(f"{source.name} -> {target.name}: {hp_damage} 伤害")
        elif absorbed > 0:
            self._record(f"{target.name} 护甲抵消 {absorbed} 伤害")
        if isinstance(target, Enemy) and target.thorn_damage and isinstance(source, Player) and skill and skill.category in {"attack", "weapon"}:
            self._deal_direct_hp_loss(source, target.thorn_damage, f"{target.name} 的尖刺")
        return hp_damage

    def _deal_weapon_damage(self, source: Fighter, target: Fighter, base: int, skill: Skill | None) -> int:
        bonus = max(0, source.dexterity)
        bonus_parts = [f"敏捷 {max(0, source.dexterity)}"]
        if isinstance(source, Player):
            for relic in source.relics:
                if relic.hook == "weapon_bonus":
                    bonus += relic.value
                    bonus_parts.append(f"{relic.name} {relic.value}")
                elif relic.hook == "status_weapon_bonus" and (target.statuses.get("poison", 0) or target.statuses.get("burn", 0)):
                    bonus += relic.value
                    bonus_parts.append(f"{relic.name} {relic.value}")
        self._record(f"武器修正：基础 {base} + {' + '.join(bonus_parts)} = {base + bonus}")
        return self._deal_damage(source, target, base + bonus, skill)

    def _group_damage_bonus(self, source: Fighter) -> int:
        if not isinstance(source, Player):
            return 0
        bonus = sum(relic.value for relic in source.relics if relic.hook == "group_damage_bonus")
        if bonus > 0:
            self._log(f"群体伤害遗物：全体伤害基础值 +{bonus}。")
        return bonus

    def _apply_poison_burst(self, source: Fighter, target: Fighter, bonus_multiplier: int) -> None:
        poison = target.statuses.get("poison", 0)
        multiplier = 150 + bonus_multiplier
        if isinstance(source, Player):
            for relic in source.relics:
                if relic.hook == "poison_burst_bonus":
                    multiplier += relic.value
        burst_damage = math.ceil(poison * multiplier / 100)
        if burst_damage <= 0:
            self._log(f"{target.name} 没有中毒，毒爆没有造成伤害。")
            self._record(f"{target.name} 毒爆未造成伤害")
            return
        dealt = self._deal_fixed_damage(source, target, burst_damage, "毒爆")
        remaining_poison = math.ceil(poison * 0.6)
        if remaining_poison > 0:
            target.statuses["poison"] = remaining_poison
        else:
            target.statuses.pop("poison", None)
        self._log(f"毒爆：{poison} 层中毒 x {multiplier}% = {burst_damage} 基础伤害，实际造成 {dealt}。")
        self._log(f"{target.name} 的中毒层数变为 {remaining_poison}。")
        self._record(f"{target.name} 毒爆：{poison} x {multiplier}% = {burst_damage}；实际 -{dealt}；中毒剩余 {remaining_poison}")

    def _apply_toxicist_passive(self, skill: Skill, damage_dealt: int, block_gained: int, target: Enemy | None = None) -> None:
        p = self.ctx.player
        enemy = target or self.ctx.enemy
        if p.role_id != "toxicist" or not enemy.alive:
            return
        poison = max(damage_dealt // 3, block_gained // 2, skill.cost * 2, 2)
        for relic in p.relics:
            if relic.hook == "toxic_passive_bonus" and poison > 0:
                poison += relic.value
        if poison <= 0:
            return
        enemy.add_status("poison", poison)
        self._log(f"诡毒师被动：{enemy.name} 获得中毒 {poison}。")
        self._record(f"诡毒师被动：{enemy.name} 中毒 +{poison}")

    def _apply_burner_passive(self) -> None:
        p = self.ctx.player
        if p.role_id != "burner":
            return
        gain = self.player_burn_applied_this_turn // 3
        if gain <= 0:
            return
        for relic in p.relics:
            if relic.hook == "burn_strength_bonus":
                gain += relic.value
        p.strength += gain
        self.player_burn_applied_this_turn = 0
        self._log(f"燃尽者被动：本回合灼烧转化为力量 +{gain}。")
        self._record(f"燃尽者被动：力量 +{gain}")

    def _apply_burner_end_powers(self) -> None:
        p = self.ctx.player
        enemy = self.ctx.enemy
        percent = p.turn_powers.get("end_burn_from_strength", 0)
        if p.role_id != "burner" or percent <= 0 or not enemy.alive:
            return
        minimum = 8 if percent >= 100 else 6
        amount = max(minimum, math.ceil(max(0, p.strength) * percent / 100))
        enemy.add_status("burn", amount)
        self.player_burn_applied_this_turn += amount
        self._log(f"生生之火：{enemy.name} 灼烧 +{amount}。")
        self._record(f"生生之火：{enemy.name} 灼烧 +{amount}")

    def _deal_fixed_damage(self, source: Fighter, target: Fighter, amount: int, reason: str) -> int:
        damage = max(0, amount)
        formula_parts = [f"基础 {amount}"]
        if source.statuses.get("weak", 0):
            damage = math.floor(damage * 0.75)
            formula_parts.append("虚弱 x0.75")
        if target.statuses.get("vulnerable", 0):
            damage = math.floor(damage * 1.5)
            formula_parts.append("易伤 x1.5")
        was_alive = isinstance(target, Enemy) and target.alive
        absorbed = min(target.block, damage)
        target.block -= absorbed
        hp_damage = damage - absorbed
        target.hp = clamp(target.hp - hp_damage, 0, target.max_hp)
        self._on_enemy_hp_loss(target, hp_damage)
        if was_alive and isinstance(target, Enemy) and not target.alive:
            self._handle_enemy_defeat(target, source, None)
        if absorbed > 0:
            self._record(f"{target.name} 护甲抵消 {absorbed} 点{reason}")
        self._log(f"{reason} 对 {target.name} 造成 {hp_damage} 伤害。")
        self._record(
            f"{reason} -> {target.name}：{' + '.join(formula_parts)} => {damage}；"
            f"护甲抵消 {absorbed}；生命 -{hp_damage}"
        )
        return hp_damage

    def _gain_block(self, target: Fighter, base: int, add_dexterity: bool = True) -> None:
        amount = base + (target.dexterity if add_dexterity else 0)
        if target.statuses.get("fragile", 0):
            amount = math.floor(amount * 0.75)
        if isinstance(target, Player):
            self.ctx.blocks_this_turn += 1
            if self.ctx.blocks_this_turn == 1:
                for relic in target.relics:
                    if relic.hook == "first_block_bonus":
                        amount += relic.value
                        self._log(f"{relic.name}：护甲 +{relic.value}。")
        target.block += max(0, amount)
        self._log(f"{target.name} 获得 {amount} 护甲。")
        self._record(f"{target.name} 获得 {amount} 护甲")

    def _tick_poison(self, fighter: Fighter) -> None:
        amount = fighter.statuses.get("poison", 0)
        if amount <= 0:
            return
        self._deal_status_damage(fighter, amount, "中毒")
        fighter.reduce_status("poison")

    def _tick_burn(self, fighter: Fighter) -> None:
        amount = fighter.statuses.get("burn", 0)
        if amount <= 0:
            return
        if isinstance(fighter, Player) and fighter.role_id == "burner":
            self._log(f"燃尽者免疫 {amount} 点灼烧伤害。")
            self._record(f"{fighter.name} 免疫 {amount} 点灼烧伤害")
        else:
            damage = amount
            if isinstance(fighter, Enemy):
                multiplier = self.ctx.player.turn_powers.pop("next_burn_multiplier", 0)
                if multiplier:
                    damage = math.ceil(amount * (100 + multiplier) / 100)
                    self._log(f"闪燃：本次灼烧伤害提高 {multiplier}%。")
            self._deal_status_damage(fighter, damage, "灼烧")
        remaining = amount // 2
        if isinstance(fighter, Enemy):
            rekindle = self.ctx.player.turn_powers.get("burn_rekindle", 0)
            if rekindle and remaining > 0:
                restored = math.ceil(remaining * rekindle / 100)
                remaining += restored
                self._log(f"不熄燃料：重新施加 {restored} 层灼烧。")
            strength_gain = self.ctx.player.turn_powers.get("burn_tick_strength", 0)
            if strength_gain and self.ctx.player.role_id == "burner":
                self.ctx.player.strength += strength_gain
                self._log(f"熔炉心脏：力量 +{strength_gain}。")
                self._record(f"{self.ctx.player.name} 力量 +{strength_gain}（熔炉心脏）")
        if remaining > 0:
            fighter.statuses["burn"] = remaining
        else:
            fighter.statuses.pop("burn", None)
        self._record(f"{fighter.name} 灼烧衰减为 {remaining}")

    def _tick_bleed(self, fighter: Fighter) -> None:
        amount = fighter.statuses.get("bleed", 0)
        if amount <= 0:
            return
        self._deal_direct_hp_loss(fighter, amount, "流血")
        fighter.reduce_status("bleed")

    def _deal_status_damage(self, fighter: Fighter, amount: int, reason: str) -> int:
        damage = max(0, amount)
        was_alive = isinstance(fighter, Enemy) and fighter.alive
        absorbed = min(fighter.block, damage)
        fighter.block -= absorbed
        hp_damage = min(damage - absorbed, fighter.hp)
        fighter.hp = clamp(fighter.hp - hp_damage, 0, fighter.max_hp)
        self._on_enemy_hp_loss(fighter, hp_damage)
        if was_alive and isinstance(fighter, Enemy) and not fighter.alive:
            self._handle_enemy_defeat(fighter)
        if absorbed:
            self._log(f"{reason}：{fighter.name} 的护甲抵消 {absorbed} 点伤害。")
            self._record(f"{fighter.name} 护甲抵消 {absorbed} 点{reason}")
        self._log(f"{reason}：{fighter.name} 失去 {hp_damage} 生命。")
        self._record(f"{fighter.name} 受到 {hp_damage} 伤害（{reason}）")
        return hp_damage

    def _tick_regeneration(self, fighter: Fighter) -> None:
        amount = fighter.statuses.get("regeneration", 0)
        if amount <= 0:
            return
        healed = min(amount, fighter.max_hp - fighter.hp)
        fighter.hp += healed
        fighter.reduce_status("regeneration")
        self._log(f"再生：{fighter.name} 回复 {healed} 生命。")
        self._record(f"{fighter.name} 回复 {healed} 生命（再生）")

    @staticmethod
    def _card_key(card: Skill) -> tuple[str, int, int]:
        return card.id, card.upgrade_level, card.cost

    def _available_deck(self, exclude_hand: bool = False) -> list[Skill]:
        unavailable = self.exhausted_cards.copy()
        if exclude_hand:
            unavailable.update(self._card_key(card) for card in self.hand)
        cards: list[Skill] = []
        for card in self.ctx.player.skills:
            key = self._card_key(card)
            if unavailable[key] > 0:
                unavailable[key] -= 1
            else:
                cards.append(card)
        return cards

    def _draw_cards(self, count: int) -> None:
        room = max(0, 10 - len(self.hand))
        drawn = choose_many(self._available_deck(exclude_hand=True), min(count, room))
        self.hand.extend(drawn)
        self._log(f"抽取 {len(drawn)} 张牌。")
        self._record(f"抽牌 {len(drawn)}")

    def _exhaust_card(self, card: Skill) -> None:
        self.exhausted_cards[self._card_key(card)] += 1
        self._log(f"{card.name} 被消耗，本场战斗不再进入手牌。")
        for relic in self.ctx.player.relics:
            if relic.hook == "exhaust_block":
                self._gain_block(self.ctx.player, relic.value, add_dexterity=False)

    def _exhaust_hand(self, current: Skill | None, include_self: bool) -> int:
        cards: list[Skill] = []
        kept_current = False
        for card in self.hand:
            if not kept_current and card is current:
                kept_current = True
                continue
            cards.append(card)
        for card in cards:
            self._exhaust_card(card)
        self.hand = [current] if kept_current and current is not None else []
        if include_self and current is not None:
            self._exhaust_card(current)
            return len(cards) + 1
        return len(cards)

    def _deal_direct_hp_loss(self, fighter: Fighter, amount: int, reason: str) -> None:
        was_alive = isinstance(fighter, Enemy) and fighter.alive
        actual = min(max(0, amount), fighter.hp)
        fighter.hp = clamp(fighter.hp - actual, 0, fighter.max_hp)
        self._on_enemy_hp_loss(fighter, actual)
        if was_alive and isinstance(fighter, Enemy) and not fighter.alive:
            self._handle_enemy_defeat(fighter)
        self._log(f"{reason}：{fighter.name} 失去 {actual} 生命。")
        self._record(f"{fighter.name} 受到 {actual} 伤害（{reason}）")

    def _handle_enemy_defeat(self, enemy: Enemy, source: Fighter | None = None, skill: Skill | None = None) -> None:
        marker = id(enemy)
        if marker in self.defeated_enemy_ids or enemy.alive:
            return
        self.defeated_enemy_ids.add(marker)
        death_poison = enemy.mechanics.get("death_poison", 0)
        if death_poison > 0:
            self.ctx.player.add_status("poison", death_poison)
            self._log(f"{enemy.name} 毒囊爆裂：{self.ctx.player.name} 中毒 +{death_poison}。")
            self._record(f"{self.ctx.player.name} 中毒 +{death_poison}（毒囊爆裂）")
        if isinstance(source, Player) and skill is not None and skill.category in {"attack", "weapon"}:
            splash = sum(relic.value for relic in source.relics if relic.hook == "overkill_splash")
            if splash > 0:
                others = [foe for foe in self.living_enemies() if foe is not enemy]
                if others:
                    self._log(f"裂刃碎片：击杀溅射，对其余敌人造成 {splash} 点伤害。")
                    for foe in others:
                        self._deal_fixed_damage(source, foe, splash, "击杀溅射")
        self._retarget_if_needed()

    def _on_enemy_hp_loss(self, fighter: Fighter, amount: int) -> None:
        if amount <= 0 or not isinstance(fighter, Enemy) or fighter.boss_id != "baiye":
            return
        fighter.strength += 1
        fighter.dexterity += 1
        self._log(f"Baiye 受创适应：力量 +1，敏捷 +1。")
        self._record(f"Baiye 力量/敏捷 +1（受创）")

    def _decay_statuses(self, fighter: Fighter) -> None:
        for status in ["vulnerable", "weak", "fragile"]:
            fighter.reduce_status(status)

    def _after_battle(self) -> None:
        p = self.ctx.player
        for relic in p.relics:
            if relic.hook == "after_battle_heal":
                p.hp = clamp(p.hp + relic.value, 0, p.max_hp)
                self._log(f"{relic.name}：回复 {relic.value} 生命。")
        p.strength = self.start_strength
        p.dexterity = self.start_dexterity

    def _print_state(self) -> None:
        clear_screen()
        p = self.ctx.player
        e = self.ctx.enemy
        intent = e.current_move.intent if e.current_move else "未知"
        left_lines = [
            "=" * 54,
            f"第 {self.ctx.turn} 回合 | {p.name} HP {p.hp}/{p.max_hp} 护甲 {p.block} 能量 {p.energy}/{p.energy_max}",
            f"状态：{status_text(p.statuses)} | 力量 {p.strength} 敏捷 {p.dexterity}",
            f"{e.name} HP {e.hp}/{e.max_hp} 护甲 {e.block} | 意图：{intent}",
            f"敌人状态：{status_text(e.statuses)} | 力量 {e.strength}",
            "-" * 54,
        ]
        for i, card in enumerate(self.hand, 1):
            preview = self._skill_preview(card)
            suffix = f" | 当前：{preview}" if preview else ""
            left_lines.append(f"{i}. [{card.cost}] {card.name} - {card.description}{suffix}")
        if self.ctx.log:
            left_lines.append("-" * 54)
            left_lines.append("最近行动：")
            for line in self.ctx.log[-6:]:
                left_lines.append(f"- {line}")
        left_lines.append("end. 结束回合 | log. 日志 | skills. 技能池 | relics. 遗物")
        print()
        for line in left_lines:
            print(line)

    def _skill_preview(self, skill: Skill) -> str:
        parts: list[str] = []
        for effect in skill.effects:
            if effect.kind == "damage":
                damage = self._preview_damage(effect.value)
                label = f"伤害 {damage}"
                if effect.times > 1:
                    label += f" x{effect.times}"
                parts.append(label)
            elif effect.kind == "damage_all":
                damage = self._preview_damage(effect.value)
                label = f"全体伤害 {damage}"
                if effect.times > 1:
                    label += f" x{effect.times}"
                parts.append(label)
            elif effect.kind == "damage_all_per_enemy":
                base = effect.value + len(self.living_enemies()) * effect.times
                parts.append(f"全体伤害 {self._preview_damage(base)}（敌人数 {len(self.living_enemies())}）")
            elif effect.kind == "weapon_damage":
                damage = self._preview_damage(effect.value + max(0, self.ctx.player.dexterity), weapon=True)
                label = f"武器伤害 {damage}"
                if effect.times > 1:
                    label += f" x{effect.times}"
                parts.append(label)
            elif effect.kind == "lifesteal_damage":
                damage = self._preview_damage(effect.value)
                heal = max(1, damage // 2 + max(0, self.ctx.player.strength) + max(0, self.ctx.player.dexterity))
                for relic in self.ctx.player.relics:
                    if relic.hook == "lifesteal_bonus":
                        heal += relic.value
                parts.append(f"伤害 {damage} / 吸血约 {heal}")
            elif effect.kind == "block":
                parts.append(f"护甲 {max(0, effect.value + self.ctx.player.dexterity)}")
            elif effect.kind == "block_per_enemy":
                amount = effect.value + len(self.living_enemies()) * effect.times
                parts.append(f"护甲 {max(0, amount + self.ctx.player.dexterity)}（敌人数 {len(self.living_enemies())}）")
            elif effect.kind == "damage_from_block":
                parts.append(f"护甲联动伤害 {math.ceil(self.ctx.player.block * effect.value / 100)}")
            elif effect.kind == "block_from_strength":
                parts.append(f"力量护甲 {max(0, self.ctx.player.strength * effect.value)}")
            elif effect.kind == "block_with_strength":
                amount = effect.value + max(0, self.ctx.player.strength) * effect.times
                parts.append(f"护甲 {amount}（{effect.value}+力量x{effect.times}）")
            elif effect.kind == "block_from_enemy_poison":
                parts.append(f"中毒护甲 {math.ceil(self.ctx.enemy.statuses.get('poison', 0) * effect.value / 100)}")
            elif effect.kind == "poison_burst":
                poison = self.ctx.enemy.statuses.get("poison", 0)
                multiplier = 150 + effect.value
                for relic in self.ctx.player.relics:
                    if relic.hook == "poison_burst_bonus":
                        multiplier += relic.value
                base_damage = math.ceil(poison * multiplier / 100)
                expected = self._preview_fixed_damage(base_damage)
                parts.append(f"毒爆 基础{base_damage}/预计扣血{expected}")
            elif effect.kind == "draw":
                parts.append(f"抽牌 {effect.value}")
            elif effect.kind == "poison_all":
                parts.append(f"全体中毒 {effect.value}")
            elif effect.kind == "burn_all":
                parts.append(f"全体灼烧 {effect.value}")
            elif effect.kind == "weak_all":
                parts.append(f"全体虚弱 {effect.value}")
            elif effect.kind == "vulnerable_all":
                parts.append(f"全体易伤 {effect.value}")
            elif effect.kind == "poison_burst_all":
                parts.append("全体毒爆")
            elif effect.kind == "damage_from_burn_all":
                total = sum(math.ceil(enemy.statuses.get("burn", 0) * effect.value / 100) for enemy in self.living_enemies())
                parts.append(f"全体灼烧追击合计 {total}")
            elif effect.kind == "energy":
                parts.append(f"能量 +{effect.value}")
            elif effect.kind == "exhaust_hand_damage":
                damage = len(self.hand) * effect.value + max(0, self.ctx.player.strength) + max(0, self.ctx.player.dexterity)
                parts.append(f"消耗整手，当前基础伤害 {damage}")
            elif effect.kind == "exhaust_hand_poison":
                parts.append(f"消耗其他手牌，当前中毒 {max(0, len(self.hand) - 1) * effect.value}")
            elif effect.kind == "exhaust_hand_burn":
                parts.append(f"消耗其他手牌，当前灼烧 {max(0, len(self.hand) - 1) * effect.value}")
            elif effect.kind == "draw_if_weak":
                parts.append(f"虚弱时抽 {effect.value}")
            elif effect.kind == "damage_per_debuff":
                layers = sum(self.ctx.enemy.statuses.get(status, 0) for status in ("weak", "vulnerable", "fragile"))
                parts.append(f"状态追加伤害 {layers * effect.value}")
            elif effect.kind == "consume_debuffs":
                layers = sum(self.ctx.enemy.statuses.get(status, 0) for status in ("weak", "vulnerable", "fragile"))
                parts.append(f"可收割 {layers} 层")
            elif effect.kind == "damage_from_burn":
                parts.append(f"灼烧追击 {math.ceil(self.ctx.enemy.statuses.get('burn', 0) * effect.value / 100)}")
            elif effect.kind == "strength_finisher":
                base = 28 if skill.upgrade_level >= 1 else 20
                threshold = 25 if skill.upgrade_level >= 1 else 30
                amount = base + max(0, self.ctx.player.strength) * effect.value
                if self.ctx.enemy.statuses.get("burn", 0) >= threshold:
                    amount = math.floor(amount * 1.5)
                parts.append(f"终结伤害 {self._preview_fixed_damage(amount)}")
        return "，".join(parts)

    def _preview_damage(self, base: int, weapon: bool = False) -> int:
        damage = base + self.ctx.player.strength
        for relic in self.ctx.player.relics:
            if relic.hook == "attack_bonus":
                damage += relic.value
            elif weapon and relic.hook == "weapon_bonus":
                damage += relic.value
            elif weapon and relic.hook == "status_weapon_bonus" and (self.ctx.enemy.statuses.get("poison", 0) or self.ctx.enemy.statuses.get("burn", 0)):
                damage += relic.value
        if self.ctx.player.statuses.get("weak", 0):
            damage = math.floor(damage * 0.75)
        if self.ctx.enemy.statuses.get("vulnerable", 0):
            damage = math.floor(damage * 1.5)
        return max(0, damage)

    def _preview_fixed_damage(self, base: int) -> int:
        damage = max(0, base)
        if self.ctx.player.statuses.get("weak", 0):
            damage = math.floor(damage * 0.75)
        if self.ctx.enemy.statuses.get("vulnerable", 0):
            damage = math.floor(damage * 1.5)
        return max(0, damage - self.ctx.enemy.block)

    def _print_log(self) -> None:
        clear_screen()
        print("\n最近日志：")
        for line in self.ctx.log[-12:]:
            print(f"- {line}")
        self._pause()

    def _print_skills(self) -> None:
        clear_screen()
        print("\n技能池：")
        for skill in self.ctx.player.skills:
            print(f"- [{skill.cost}] {skill.name}: {skill.description}")
        self._pause()

    def _print_relics(self) -> None:
        clear_screen()
        print("\n遗物：")
        if not self.ctx.player.relics:
            print("- 无")
        for relic in self.ctx.player.relics:
            print(f"- {relic.name}: {relic.description}")
        self._pause()

    def _log(self, text: str) -> None:
        self.ctx.log.append(text)

    def _record(self, text: str) -> None:
        self.turn_records.append(text)
        if len(self.turn_records) > 20:
            self.turn_records = self.turn_records[-20:]

    def _pause(self) -> None:
        input("\n按回车返回当前回合...")

    def _status_name(self, status: str) -> str:
        return {
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
            "energy_debt": "下回合能量透支",
            "next_energy": "下回合能量",
            "next_draw": "下回合抽牌",
            "burn_tick_strength": "灼烧结算成长",
            "end_burn_from_strength": "力量续火",
            "next_burn_multiplier": "闪燃增幅",
            "burn_rekindle": "灼烧复燃",
            "burn_on_card": "出牌点火",
        }.get(status, status)
