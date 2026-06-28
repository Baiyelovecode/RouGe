from __future__ import annotations

import random

from game.combat import Combat
from game.catalog import browse_card_catalog, browse_relic_catalog
from game.data import SKILLS, boss_enemy, create_player, elite_enemy, normal_enemy, random_relic, random_relics, reward_skills, shop_skill_offers, starting_player
from game.models import Player, Relic, Skill
from game.util import clamp, clear_screen, input_choice


class Game:
    def __init__(self) -> None:
        self.player: Player = starting_player()
        self.floor = 1
        self.act = 1

    def run(self) -> None:
        self._intro()
        if not self._start_menu():
            return
        self._choose_role()
        while self.act <= 4 and self.player.alive:
            for floor_in_act in range(1, 9):
                self.floor = (self.act - 1) * 8 + floor_in_act
                print(f"\n{'=' * 64}\n第 {self.act} 章 / 第 {floor_in_act} 层（总第 {self.floor} 层）")
                node = "boss" if floor_in_act == 8 else self._choose_node(floor_in_act)
                if not self._resolve_node(node):
                    return
                self._after_floor_clear()
            self.act += 1
        if self.player.alive:
            print("\n你击碎了塔心。通关！")

    def _intro(self) -> None:
        print("数值之塔 CLI 原型")
        print("参考杀戮尖塔：能量、技能选择、敌人意图、战斗奖励、遗物构筑。")
        print("武器牌规则：每段武器伤害 = 卡面基础值 + 当前力量 + 当前敏捷，再计算状态与遗物。")
        print("输入数字选择；战斗中可输入 end/log/skills/relics。")

    def _start_menu(self) -> bool:
        while True:
            print("\n1. 开始游戏")
            print("2. 卡牌图鉴（展示全部等级）")
            print("3. 遗物图鉴（展示适用角色）")
            print("4. 退出")
            choice = input_choice("> ", {"1", "2", "3", "4"})
            if choice == "1":
                return True
            if choice == "2":
                browse_card_catalog()
            elif choice == "3":
                browse_relic_catalog()
            else:
                return False

    def _choose_role(self) -> None:
        print("\n选择角色：")
        print("1. 流亡者：每场战斗开始获得永久适应加成；每层至少 +1，约成长 18%，最高 80。")
        print("2. 诡毒师：使用卡牌后，按伤害/护甲给敌人追加中毒。初始含毒雾和毒爆。")
        print("3. 燃尽者：免疫自身灼烧伤害；灼烧转化力量，并在长线战斗中持续成长。")
        choice = input_choice("> ", {"1", "2", "3"})
        role = {"1": "exile", "2": "toxicist", "3": "burner"}[choice]
        self.player = create_player(role)
        print(f"你选择了：{self.player.name}")

    def _choose_node(self, floor_in_act: int) -> str:
        if floor_in_act == 1:
            return "combat"
        if floor_in_act == 7:
            choices = ["rest", "shop", "training"]
        else:
            pool = ["combat", "combat", "combat", "event", "event", "treasure", "shop", "rest",
                    "training", "armory"]
            if floor_in_act >= 3:
                pool.append("elite")
            choices = random.sample(pool, 4)

        names = {
            "combat": "战斗",
            "elite": "精英",
            "event": "事件",
            "shop": "商店",
            "rest": "休息",
            "treasure": "宝箱",
            "training": "训练场",
            "armory": "兵装工坊",
        }
        print("你面前有这些路线：")
        for i, node in enumerate(choices, 1):
            print(f"{i}. {names[node]}")
        choice = input_choice("> ", {str(i) for i in range(1, len(choices) + 1)})
        return choices[int(choice) - 1]

    def _resolve_node(self, node: str) -> bool:
        if node == "combat":
            return self._fight(normal_enemy(self.act))
        if node == "elite":
            won = self._fight(elite_enemy(self.act))
            if won:
                self._grant_relic()
            return won
        if node == "boss":
            won = self._fight(boss_enemy(self.act))
            if won:
                self._grant_relic()
            return won
        if node == "treasure":
            self._grant_relic()
            return True
        if node == "rest":
            self._rest()
            return True
        if node == "shop":
            self._shop()
            return True
        if node == "event":
            self._event()
            return True
        if node == "training":
            self._training()
            return True
        if node == "armory":
            self._armory()
            return True
        raise ValueError(node)

    def _fight(self, enemy) -> bool:
        won = Combat(self.player, enemy).run()
        if won:
            gold = random.randint(12, 22) + self.act * 4
            gold = self._gold_with_relics(gold)
            self.player.gold += gold
            print(f"获得 {gold} 金币。当前金币：{self.player.gold}")
            self._choose_skill_reward()
        return won

    def _after_floor_clear(self) -> None:
        if self.player.role_id != "exile":
            return
        # Layer growth is based only on the out-of-combat starter bonus.
        # Any temporary combat strength/dexterity must not leak into it.
        self.player.strength = 0
        self.player.dexterity = 0
        old = self.player.starter_bonus
        self.player.starter_bonus = min(80, max(old + 1, (old * 118 + 99) // 100))
        print(f"流亡者适应成长：开战力量/敏捷加成 {old} -> {self.player.starter_bonus}")

    def _choose_skill_reward(self, count: int = 4, title: str = "选择一个技能奖励") -> None:
        rewards = reward_skills(count)
        print(f"\n{title}：")
        for i, s in enumerate(rewards, 1):
            print(f"{i}. [{s.cost}] {s.name} - {s.description}")
        skip = len(rewards) + 1
        print(f"{skip}. 跳过")
        choice = input_choice("> ", {str(i) for i in range(1, skip + 1)})
        if choice == str(skip):
            print("你跳过了技能奖励。")
            return
        picked = rewards[int(choice) - 1]
        self.player.skills.append(picked)
        print(f"获得技能：{picked.name}")

    def _grant_relic(self) -> None:
        relic = random_relic(self.player.relics, self.player.role_id)
        if relic is None:
            print("没有新的遗物可获得。")
            return
        self.player.relics.append(relic)
        print(f"\n获得遗物：{relic.name} - {relic.description}")

    def _rest(self) -> None:
        print("\n休息点：")
        print("1. 回复 30% 最大生命")
        print("2. 从 3 张随机技能中选择 1 张升级")
        choice = input_choice("> ", {"1", "2"})
        if choice == "1":
            amount = max(1, self.player.max_hp * 30 // 100)
            self.player.hp = clamp(self.player.hp + amount, 0, self.player.max_hp)
            print(f"回复 {amount} 生命。当前生命 {self.player.hp}/{self.player.max_hp}")
        else:
            offers = self._upgrade_offers()
            if offers:
                self._choose_upgrade_offer(offers, free=True)
            else:
                print("没有可升级技能，改为回复生命。")
                self.player.hp = self.player.max_hp

    def _training(self) -> None:
        print("\n节点：训练场")
        print("1. 体魄训练：最大生命 +8，并回复 8 生命")
        print("2. 技法训练：从 3 张随机卡牌中选择 1 张升级")
        choice = input_choice("> ", {"1", "2"})
        if choice == "1":
            self.player.max_hp += 8
            self.player.hp = clamp(self.player.hp + 8, 0, self.player.max_hp)
            print(f"最大生命提升至 {self.player.max_hp}。")
            return
        offers = self._upgrade_offers()
        if offers:
            self._choose_upgrade_offer(offers, free=True)
        else:
            self.player.max_hp += 5
            self.player.hp = self.player.max_hp
            print("所有卡牌均已满级，转为最大生命 +5 并完全回复。")

    def _armory(self) -> None:
        weapons = random.sample([card for card in SKILLS.values() if card.category == "weapon"], 3)
        print("\n节点：兵装工坊")
        print("武器每段伤害均为：卡面基础值 + 力量 + 敏捷。")
        for idx, card in enumerate(weapons, 1):
            print(f"{idx}. [{card.cost}] {card.name} - {card.description}")
        print("4. 放弃兵装，获得 45 金币")
        choice = input_choice("> ", {"1", "2", "3", "4"})
        if choice == "4":
            self.player.gold += 45
            print("获得 45 金币。")
            return
        card = weapons[int(choice) - 1]
        if self.act >= 3 and random.random() < 0.5:
            card = card.upgraded_copy()
        self.player.skills.append(card)
        print(f"获得武器牌：{card.name}")

    def _choose_upgrade_offer(self, offers: list[Skill], free: bool = False) -> None:
        print("\n选择要升级的技能：")
        for idx, skill in enumerate(offers, 1):
            upgraded = skill.upgraded_copy()
            print(f"{idx}. [{skill.cost}费] {skill.name} Lv.{skill.upgrade_level} -> [{upgraded.cost}费] {upgraded.name} Lv.{upgraded.upgrade_level}")
        print(f"{len(offers) + 1}. 取消")
        valid = {str(i) for i in range(1, len(offers) + 2)}
        choice = input_choice("> ", valid)
        if choice == str(len(offers) + 1):
            return
        selected = offers[int(choice) - 1]
        if free or self._pay(60):
            self._upgrade_exact_skill(selected)

    def _shop(self) -> None:
        print(f"\n商店 | 金币：{self.player.gold}")
        skill_offers: list[Skill | None] = shop_skill_offers()
        relic_offers: list[Relic | None] = random_relics(self.player.relics, self.player.role_id, 4)
        relic_offers.extend([None] * (4 - len(relic_offers)))
        upgrade_offers: list[Skill | None] = self._upgrade_offers()
        purchases: list[str] = []
        removal_count = 0
        if not upgrade_offers:
            self.player.gold += 100
            print("你的所有技能都已经升级，商店补偿你 100 金币。")
        while True:
            clear_screen()
            print(f"\n商店 | 金币：{self.player.gold} | 生命：{self.player.hp}/{self.player.max_hp}")
            if purchases:
                print("本次已购买：" + "、".join(purchases))
            print("\n技能商品：")
            for idx, offered_skill in enumerate(skill_offers, 1):
                if offered_skill is None:
                    print(f"{idx}. [已售出]")
                    continue
                price = self._skill_price(offered_skill)
                print(f"{idx}. {price} 金币 | [{offered_skill.cost}] {offered_skill.name} Lv.{offered_skill.upgrade_level} - {offered_skill.description}")
            print("遗物商品：")
            for idx, offered_relic in enumerate(relic_offers, 4):
                if offered_relic is None:
                    print(f"{idx}. [已售出]")
                else:
                    print(f"{idx}. 90 金币 | {offered_relic.name} - {offered_relic.description}")
            print("升级服务：")
            for idx, upgrade_skill in enumerate(upgrade_offers, 8):
                if upgrade_skill is None:
                    print(f"{idx}. [已使用]")
                    continue
                upgraded = upgrade_skill.upgraded_copy()
                print(f"{idx}. 60 金币 | [{upgrade_skill.cost}费] {upgrade_skill.name} Lv.{upgrade_skill.upgrade_level} -> [{upgraded.cost}费] {upgraded.name} Lv.{upgraded.upgrade_level}")
            print("11. 回复 20 生命，35 金币")
            removal_price = 60 + removal_count * 30
            print(f"12. 移除一张卡牌，{removal_price} 金币 | 当前卡组 {len(self.player.skills)} 张")
            print("13. 离开")
            choice = input_choice("> ", {str(i) for i in range(1, 14)})
            if choice in {"1", "2", "3"}:
                index = int(choice) - 1
                if index >= len(skill_offers) or skill_offers[index] is None:
                    print("该技能商品已售罄。")
                    continue
                offered_skill = skill_offers[index]
                if self._pay(self._skill_price(offered_skill)):
                    self.player.skills.append(offered_skill)
                    purchases.append(offered_skill.name)
                    skill_offers[index] = None
            elif choice in {"4", "5", "6", "7"}:
                index = int(choice) - 4
                offered_relic = relic_offers[index]
                if offered_relic is None:
                    continue
                if self._pay(90):
                    self.player.relics.append(offered_relic)
                    purchases.append(offered_relic.name)
                    relic_offers[index] = None
            elif choice in {"8", "9", "10"}:
                index = int(choice) - 8
                if index >= len(upgrade_offers) or upgrade_offers[index] is None:
                    print("该升级服务不可用。")
                    continue
                if self._pay(60):
                    original = upgrade_offers[index]
                    self._upgrade_exact_skill(original)
                    purchases.append(f"升级 {original.name}")
                    upgrade_offers[index] = None
            elif choice == "11" and self._pay(35):
                self.player.hp = clamp(self.player.hp + 20, 0, self.player.max_hp)
                purchases.append("生命回复")
            elif choice == "12":
                if len(self.player.skills) <= 5:
                    print("卡组至少保留 5 张牌。")
                    continue
                if self.player.gold < removal_price:
                    print("金币不足。")
                    continue
                removed = self._choose_card_removal()
                if removed is not None:
                    self.player.gold -= removal_price
                    removal_count += 1
                    purchases.append(f"移除 {removed.name}")
            elif choice == "13":
                return

    def _skill_price(self, skill: Skill) -> int:
        return 70 if skill.upgrade_level > 0 else 45

    def _upgrade_offers(self) -> list[Skill]:
        candidates = [skill for skill in self.player.skills if skill.upgrade_level < 2]
        if len(candidates) <= 3:
            return candidates
        return random.sample(candidates, 3)

    def _upgrade_exact_skill(self, skill: Skill) -> None:
        for idx, owned in enumerate(self.player.skills):
            if owned is skill:
                upgraded = owned.upgraded_copy()
                self.player.skills[idx] = upgraded
                print(f"升级技能：{owned.name} -> {upgraded.name}")
                return
        print("这个技能已经不在技能池中。")

    def _choose_card_removal(self) -> Skill | None:
        print("\n选择要移除的卡牌：")
        for idx, card in enumerate(self.player.skills, 1):
            print(f"{idx}. [{card.cost}] {card.name} Lv.{card.upgrade_level} - {card.description}")
        cancel = len(self.player.skills) + 1
        print(f"{cancel}. 取消")
        choice = input_choice("> ", {str(i) for i in range(1, cancel + 1)})
        if choice == str(cancel):
            return None
        removed = self.player.skills.pop(int(choice) - 1)
        print(f"已移除：{removed.name}")
        return removed

    def _event(self) -> None:
        events = [self._event_shrine, self._event_blood, self._event_fountain,
                  self._event_forge, self._event_status_lab, self._event_role_resonance]
        random.choice(events)()

    def _event_forge(self) -> None:
        print("\n事件：无主锻炉")
        print("1. 从 5 张武器牌中选择 1 张")
        print("2. 失去 10 生命，从 3 张随机卡牌中选择 1 张升级")
        print("3. 精简兵装：移除一张卡牌")
        choice = input_choice("> ", {"1", "2", "3"})
        if choice == "1":
            weapons = [card for card in SKILLS.values() if card.category == "weapon"]
            self._choose_card_from_pool(weapons, "选择锻造兵装", count=5, upgraded_chance=0.4)
        elif choice == "2":
            self.player.hp = clamp(self.player.hp - 10, 1, self.player.max_hp)
            offers = self._upgrade_offers()
            if offers:
                self._choose_upgrade_offer(offers, free=True)
        elif len(self.player.skills) > 5:
            self._choose_card_removal()

    def _event_status_lab(self) -> None:
        print("\n事件：蚀焰实验室")
        print("1. 注入毒素：失去 8 生命，从 5 张中毒/负面牌中选择 1 张")
        print("2. 点燃炉心：最大生命 -4，从 5 张灼烧/能量牌中选择 1 张")
        print("3. 稳定实验：从 5 张状态牌中选择 1 张，不支付生命")
        choice = input_choice("> ", {"1", "2", "3"})
        if choice == "1":
            self.player.hp = clamp(self.player.hp - 8, 1, self.player.max_hp)
            ids = ["poison_blade", "poison_cloud", "toxic_guard", "septic_stab", "toxic_shell",
                   "venom_burst", "toxic_purge", "execution_mark", "opportunist", "status_harvest"]
            self._choose_card_from_pool([SKILLS[id_] for id_ in ids], "选择毒素实验成果", 5, 0.25)
        elif choice == "2":
            self.player.max_hp = max(1, self.player.max_hp - 4)
            self.player.hp = min(self.player.hp, self.player.max_hp)
            ids = ["ember_cut", "flare_guard", "inferno_seed", "wildfire", "cauterize",
                   "ember_recycle", "overclock", "reserve_cell", "scorching_chain", "flame_bastion"]
            self._choose_card_from_pool([SKILLS[id_] for id_ in ids], "选择炉心实验成果", 5, 0.25)
        else:
            ids = ["weaken", "execution_mark", "fracture_hex", "opportunist", "pressure_break",
                   "status_harvest", "bloodletting", "renewal"]
            self._choose_card_from_pool([SKILLS[id_] for id_ in ids], "选择状态实验成果", 5)

    def _event_role_resonance(self) -> None:
        rewards = {
            "toxicist": "venom_fang",
            "burner": "cinder_greatsword",
            "exile": "power_blade",
        }
        card = SKILLS[rewards[self.player.role_id]].upgraded_copy()
        print(f"\n事件：兵装共鸣\n{self.player.name} 与 {card.name} 产生共鸣。")
        print("1. 从 5 张角色联动牌中选择 1 张升级牌")
        print("2. 将 3 张随机卡牌中的 1 张升级")
        choice = input_choice("> ", {"1", "2"})
        if choice == "1":
            role_cards = {
                "exile": ["power_blade", "dancer_blades", "balanced_form", "pressure_break", "battle_flow"],
                "toxicist": ["venom_fang", "toxic_shell", "venom_burst", "toxic_purge", "plague_cut"],
                "burner": ["furnace_heart", "fire_cycle", "flashover", "cinder_engine", "solar_collapse",
                           "cinder_greatsword", "inferno_seed", "cauterize", "ember_recycle", "flame_bastion"],
            }
            self._choose_card_from_pool([SKILLS[id_] for id_ in role_cards[self.player.role_id]],
                                        "选择共鸣卡牌", 5, 1.0)
        else:
            offers = self._upgrade_offers()
            if offers:
                self._choose_upgrade_offer(offers, free=True)

    def _event_shrine(self) -> None:
        print("\n事件：破损祭坛")
        print("1. 失去 12 生命，获得遗物")
        print("2. 获得 50 金币")
        print("3. 离开")
        choice = input_choice("> ", {"1", "2", "3"})
        if choice == "1":
            self.player.hp = clamp(self.player.hp - 12, 1, self.player.max_hp)
            self._grant_relic()
        elif choice == "2":
            self.player.gold += 50
            print("获得 50 金币。")

    def _event_blood(self) -> None:
        print("\n事件：血字契约")
        print("1. 最大生命 -6，选择一个技能")
        print("2. 回复 15 生命")
        choice = input_choice("> ", {"1", "2"})
        if choice == "1":
            self.player.max_hp -= 6
            self.player.hp = clamp(self.player.hp, 1, self.player.max_hp)
            self._choose_skill_reward(5, "从 5 张契约卡牌中选择 1 张")
        else:
            self.player.hp = clamp(self.player.hp + 15, 0, self.player.max_hp)
            print(f"当前生命 {self.player.hp}/{self.player.max_hp}")

    def _event_fountain(self) -> None:
        print("\n事件：清泉")
        print("你恢复了 25% 最大生命。")
        self.player.hp = clamp(self.player.hp + self.player.max_hp // 4, 0, self.player.max_hp)

    def _choose_card_from_pool(self, pool: list[Skill], title: str, count: int = 5,
                               upgraded_chance: float = 0.0) -> Skill | None:
        offers = random.sample(pool, min(count, len(pool)))
        offers = [card.upgraded_copy() if random.random() < upgraded_chance else card for card in offers]
        print(f"\n{title}：")
        for idx, card in enumerate(offers, 1):
            print(f"{idx}. [{card.cost}] {card.name} Lv.{card.upgrade_level} - {card.description}")
        cancel = len(offers) + 1
        print(f"{cancel}. 放弃")
        choice = input_choice("> ", {str(i) for i in range(1, cancel + 1)})
        if choice == str(cancel):
            return None
        picked = offers[int(choice) - 1]
        self.player.skills.append(picked)
        print(f"获得技能：{picked.name}")
        return picked

    def _pay(self, amount: int) -> bool:
        if self.player.gold < amount:
            print("金币不足。")
            return False
        self.player.gold -= amount
        return True

    def _gold_with_relics(self, amount: int) -> int:
        for relic in self.player.relics:
            if relic.id == "greedy_coin":
                amount = amount * 125 // 100
        return amount
