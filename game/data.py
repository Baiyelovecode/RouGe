from __future__ import annotations

import math
import random

from game.models import Effect, Enemy, EnemyMove, Player, Relic, Skill


ACT_FLOOR_COUNTS = {
    4: 12,
}


def act_floor_count(act: int) -> int:
    return ACT_FLOOR_COUNTS.get(act, 8)


def act_start_floor(act: int) -> int:
    return 1 + sum(act_floor_count(previous) for previous in range(1, act))


def skill(
    id_: str,
    name: str,
    cost: int,
    category: str,
    rarity: str,
    description: str,
    effects: list[Effect],
    upgraded: bool = False,
    upgrade_level: int | None = None,
) -> Skill:
    level = upgrade_level if upgrade_level is not None else (1 if upgraded else 0)
    return Skill(id_, name, cost, category, rarity, description, tuple(effects), upgraded, level)


SKILLS: dict[str, Skill] = {
    "strike": skill("strike", "斩击", 1, "attack", "basic", "造成 6 点伤害。", [Effect("damage", 6)]),
    "defend": skill("defend", "格挡", 1, "defense", "basic", "获得 5 点护甲。", [Effect("block", 5, "self")]),
    "bash": skill("bash", "重击", 2, "attack", "basic", "造成 14 点伤害。", [Effect("damage", 14)]),
    "warcry": skill("warcry", "战意", 1, "power", "basic", "本场战斗力量 +3。", [Effect("strength", 3, "self")]),
    "pierce": skill("pierce", "破甲斩", 1, "attack", "common", "造成 5 点伤害，施加 2 层易伤。", [Effect("damage", 5), Effect("vulnerable", 2)]),
    "poison_blade": skill("poison_blade", "毒刃", 1, "attack", "common", "造成 4 点伤害，施加 3 层中毒。", [Effect("damage", 4), Effect("poison", 3)]),
    "quick_stab": skill("quick_stab", "迅捷刺击", 0, "attack", "common", "造成 3 点伤害。", [Effect("damage", 3)]),
    "double_hit": skill("double_hit", "双重打击", 1, "attack", "common", "造成 4 点伤害 2 次。", [Effect("damage", 4, times=2)]),
    "iron_wall": skill("iron_wall", "铁壁", 2, "defense", "common", "获得 14 点护甲。", [Effect("block", 14, "self")]),
    "sidestep": skill("sidestep", "闪身", 0, "defense", "common", "获得 3 点护甲。", [Effect("block", 3, "self")]),
    "guarded_thrust": skill("guarded_thrust", "盾刺", 1, "attack", "common", "造成 5 点伤害，获得 5 点护甲。", [Effect("damage", 5), Effect("block", 5, "self")]),
    "sweeping_strike": skill("sweeping_strike", "横扫", 1, "attack", "common", "对所有敌人造成 5 点伤害。", [Effect("damage_all", 5)]),
    "blade_storm": skill("blade_storm", "刃风", 2, "attack", "uncommon", "对所有敌人造成 9 点伤害。", [Effect("damage_all", 9)]),
    "agility": skill("agility", "灵巧", 1, "power", "uncommon", "本场战斗敏捷 +3。", [Effect("dexterity", 3, "self")]),
    "burn": skill("burn", "燃烧术", 2, "skill", "uncommon", "施加 16 层灼烧。", [Effect("burn", 16)]),
    "ember_cut": skill("ember_cut", "余烬斩", 1, "attack", "common", "造成 8 点伤害，施加 8 层灼烧。", [Effect("damage", 8), Effect("burn", 8)]),
    "flare_guard": skill("flare_guard", "火幕", 1, "defense", "common", "获得 9 点护甲，施加 7 层灼烧。", [Effect("block", 9, "self"), Effect("burn", 7)]),
    "inferno_seed": skill("inferno_seed", "燃核", 2, "power", "rare", "本场战斗力量 +4，并施加 20 层灼烧。", [Effect("strength", 4, "self"), Effect("burn", 20)]),
    "scorching_chain": skill("scorching_chain", "灼链", 1, "skill", "uncommon", "施加 11 层灼烧和 2 层虚弱。", [Effect("burn", 11), Effect("weak", 2)]),
    "ash_armor": skill("ash_armor", "灰烬护甲", 2, "defense", "uncommon", "获得 18 点护甲，施加 12 层灼烧。", [Effect("block", 18, "self"), Effect("burn", 12)]),
    "wildfire": skill("wildfire", "燎原", 2, "skill", "rare", "施加 20 层灼烧和 2 层易伤。", [Effect("burn", 20), Effect("vulnerable", 2)]),
    "firestorm": skill("firestorm", "火雨", 2, "skill", "uncommon", "对所有敌人施加 12 层灼烧。", [Effect("burn_all", 12)]),
    "poison_cloud": skill("poison_cloud", "毒雾", 2, "skill", "uncommon", "施加 12 层中毒。", [Effect("poison", 12)]),
    "plague_mist": skill("plague_mist", "疫雾", 2, "skill", "uncommon", "对所有敌人施加 8 层中毒。", [Effect("poison_all", 8)]),
    "toxic_guard": skill("toxic_guard", "毒障", 1, "defense", "common", "获得 10 点护甲，施加 5 层中毒。", [Effect("block", 10, "self"), Effect("poison", 5)]),
    "venom_math": skill("venom_math", "毒算", 0, "skill", "uncommon", "施加 3 层中毒。若敌人已有中毒，额外施加 3 层。", [Effect("poison", 3), Effect("poison_if_poisoned", 3)]),
    "septic_stab": skill("septic_stab", "腐蚀刺", 1, "attack", "common", "造成 7 点伤害，施加 5 层中毒和 2 层易伤。", [Effect("damage", 7), Effect("poison", 5), Effect("vulnerable", 2)]),
    "plague_wall": skill("plague_wall", "疫墙", 2, "defense", "rare", "获得 20 点护甲。若敌人已中毒，额外施加 10 层中毒。", [Effect("block", 20, "self"), Effect("poison_if_poisoned", 10)]),
    "weaken": skill("weaken", "虚弱打击", 1, "attack", "common", "造成 9 点伤害，施加 3 层虚弱。虚弱使攻击伤害降低 25%。", [Effect("damage", 9), Effect("weak", 3)]),
    "focus": skill("focus", "蓄势", 1, "power", "uncommon", "下次攻击伤害 +8。", [Effect("next_attack", 8, "self")]),
    "guard_oath": skill("guard_oath", "坚守", 1, "power", "rare", "本场战斗每回合开始获得 3 点护甲。", [Effect("ritual_block", 3, "self")]),
    "hold_guard": skill("hold_guard", "固守阵线", 2, "power", "rare", "本场战斗护甲不会在回合开始时清空。", [Effect("retain_block", 1, "self")]),
    "blood_slash": skill("blood_slash", "饮血斩", 1, "attack", "common", "造成 7 点伤害，按实际伤害、力量和敏捷回复生命。", [Effect("lifesteal_damage", 7)]),
    "crimson_rush": skill("crimson_rush", "猩红突袭", 2, "attack", "uncommon", "造成 13 点伤害，按实际伤害、力量和敏捷回复生命。", [Effect("lifesteal_damage", 13)]),
    "blood_guard": skill("blood_guard", "血盾", 1, "defense", "uncommon", "获得 10 点护甲，本场战斗敏捷 +3。", [Effect("block", 10, "self"), Effect("dexterity", 3, "self")]),
    "red_harvest": skill("red_harvest", "赤色收割", 2, "attack", "rare", "造成 9 点吸血伤害，并施加 2 层易伤。", [Effect("lifesteal_damage", 9), Effect("vulnerable", 2)]),
    "venom_burst": skill("venom_burst", "毒爆", 1, "skill", "uncommon", "造成敌人中毒层数 1.5 倍伤害，随后中毒变为 60%。", [Effect("poison_burst", 0)]),
    "plague_cut": skill("plague_cut", "疫刃收割", 2, "attack", "rare", "造成 12 点伤害，再触发毒爆。", [Effect("damage", 12), Effect("poison_burst", 0)]),
    "balanced_form": skill("balanced_form", "均衡姿态", 2, "power", "rare", "本场战斗力量 +3，敏捷 +3，获得 14 点护甲。", [Effect("strength", 3, "self"), Effect("dexterity", 3, "self"), Effect("block", 14, "self")]),
    "execution_mark": skill("execution_mark", "处决标记", 1, "skill", "uncommon", "施加 3 层易伤和 3 层虚弱。", [Effect("vulnerable", 3), Effect("weak", 3)]),
    "war_banner": skill("war_banner", "破阵战旗", 2, "skill", "rare", "对所有敌人施加 2 层虚弱和 2 层易伤。", [Effect("weak_all", 2), Effect("vulnerable_all", 2)]),
    "linebreaker": skill("linebreaker", "破线斩", 1, "attack", "common", "对所有敌人造成 4 + 存活敌人数 x2 点伤害。", [Effect("damage_all_per_enemy", 4, times=2)]),
    "shield_wall": skill("shield_wall", "盾墙推进", 1, "defense", "common", "获得 6 + 存活敌人数 x3 点护甲。", [Effect("block_per_enemy", 6, "self", times=3)]),
    "toxic_bloom": skill("toxic_bloom", "毒花绽放", 2, "skill", "rare", "对所有敌人施加 7 层中毒，再对所有敌人触发 1.2 倍毒爆。", [Effect("poison_all", 7), Effect("poison_burst_all", -30)]),
    "ash_surge": skill("ash_surge", "灰烬浪潮", 2, "skill", "uncommon", "对所有敌人施加 8 层灼烧，并追加其当前灼烧 40% 的伤害。", [Effect("burn_all", 8), Effect("damage_from_burn_all", 40)]),
    "blade_maelstrom": skill("blade_maelstrom", "乱刃风暴", 2, "attack", "rare", "对所有敌人造成 7 点伤害 2 次。", [Effect("damage_all", 7, times=2)]),
    "fortress_bash": skill("fortress_bash", "城塞反击", 2, "attack", "uncommon", "获得 12 点护甲，并造成当前护甲 50% 的伤害。", [Effect("block", 12, "self"), Effect("damage_from_block", 50)]),
    "iron_breath": skill("iron_breath", "铁壁吐息", 2, "defense", "uncommon", "一次性获得 8 + 力量 x2 的护甲。", [Effect("block_with_strength", 8, "self", times=2)]),
    "toxic_shell": skill("toxic_shell", "毒甲共生", 2, "defense", "rare", "获得 12 点护甲，再获得敌人中毒层数等量的护甲。", [Effect("block", 12, "self"), Effect("block_from_enemy_poison", 100, "self")]),
    "flame_bastion": skill("flame_bastion", "焚城壁垒", 3, "defense", "rare", "获得 26 点护甲，并施加 20 层灼烧。", [Effect("block", 26, "self"), Effect("burn", 20)]),
    "power_blade": skill("power_blade", "力铸长刃", 2, "weapon", "uncommon", "武器：造成 16 + 力量 + 敏捷伤害；本场力量 +3。", [Effect("weapon_damage", 16), Effect("strength", 3, "self")]),
    "dancer_blades": skill("dancer_blades", "双舞短刃", 2, "weapon", "uncommon", "武器：造成 8 + 力量 + 敏捷伤害 2 次；本场敏捷 +3。", [Effect("weapon_damage", 8, times=2), Effect("dexterity", 3, "self")]),
    "venom_fang": skill("venom_fang", "淬毒蛇牙", 2, "weapon", "rare", "武器：造成 14 + 力量 + 敏捷伤害，并施加 16 层中毒。", [Effect("weapon_damage", 14), Effect("poison", 16)]),
    "cinder_greatsword": skill("cinder_greatsword", "烬火巨剑", 3, "weapon", "rare", "武器：造成 28 + 力量 + 敏捷伤害，并施加 28 层灼烧。", [Effect("weapon_damage", 28), Effect("burn", 28)]),
    "bulwark_hammer": skill("bulwark_hammer", "壁垒战锤", 3, "weapon", "rare", "武器：获得 24 点护甲，造成 12 + 力量 + 敏捷伤害，再造成当前护甲 25% 的伤害。", [Effect("block", 24, "self"), Effect("weapon_damage", 12), Effect("damage_from_block", 25)]),
    "cauterize": skill("cauterize", "炽痕引燃", 2, "skill", "uncommon", "施加 16 层灼烧；敌人已有灼烧时额外施加其当前灼烧的 50%。", [Effect("burn", 16), Effect("burn_echo", 50)]),
    "battle_flow": skill("battle_flow", "战术流转", 1, "skill", "common", "抽 2 张牌。", [Effect("draw", 2, "self")]),
    "adrenaline": skill("adrenaline", "肾上腺素", 0, "skill", "rare", "获得 1 点能量，抽 1 张牌。消耗。", [Effect("energy", 1, "self"), Effect("draw", 1, "self"), Effect("exhaust_self", 1, "self")]),
    "overclock": skill("overclock", "超载驱动", 0, "skill", "uncommon", "获得 2 点能量；下回合能量 -1。消耗。", [Effect("energy", 2, "self"), Effect("energy_debt", 1, "self"), Effect("exhaust_self", 1, "self")]),
    "reserve_cell": skill("reserve_cell", "储能电池", 1, "power", "uncommon", "下回合获得 2 点额外能量并额外抽 1 张牌。", [Effect("next_energy", 2, "self"), Effect("next_draw", 1, "self")]),
    "bloodletting": skill("bloodletting", "放血刃", 1, "attack", "common", "造成 8 点伤害并施加 5 层流血。流血在回合结束造成伤害并减少 1 层。", [Effect("damage", 8), Effect("bleed", 5)]),
    "fracture_hex": skill("fracture_hex", "碎甲咒", 1, "skill", "uncommon", "施加 2 层脆弱与 1 层易伤。脆弱使获得的护甲降低 25%。", [Effect("fragile", 2), Effect("vulnerable", 1)]),
    "renewal": skill("renewal", "再生脉冲", 1, "skill", "uncommon", "获得 6 层再生。每回合开始回复生命并减少 1 层。", [Effect("regeneration", 6, "self")]),
    "hand_detonation": skill("hand_detonation", "孤注一掷", 2, "attack", "rare", "消耗所有手牌；造成消耗数量 x7 + 力量 + 敏捷的伤害。", [Effect("exhaust_hand_damage", 7)]),
    "toxic_purge": skill("toxic_purge", "毒囊清仓", 1, "skill", "rare", "消耗除本牌外的所有手牌；每消耗 1 张，施加 5 层中毒。", [Effect("exhaust_hand_poison", 5)]),
    "ember_recycle": skill("ember_recycle", "余烬回收", 1, "skill", "rare", "消耗除本牌外的所有手牌；每消耗 1 张，施加 7 层灼烧并获得 1 点护甲。", [Effect("exhaust_hand_burn", 7)]),
    "opportunist": skill("opportunist", "乘隙追击", 1, "attack", "uncommon", "造成 10 点伤害；目标处于虚弱时额外抽 2 张牌。", [Effect("damage", 10), Effect("draw_if_weak", 2, "self")]),
    "pressure_break": skill("pressure_break", "压制破阵", 2, "attack", "rare", "造成 18 点伤害；目标每有 1 层虚弱、易伤或脆弱，额外造成 6 点伤害。", [Effect("damage", 18), Effect("damage_per_debuff", 6)]),
    "status_harvest": skill("status_harvest", "状态收割", 2, "skill", "rare", "移除敌人全部虚弱、易伤和脆弱；每移除 1 层获得 1 点能量和 3 点护甲。", [Effect("consume_debuffs", 3)]),
    "ember_breath": skill("ember_breath", "纳火吐息", 0, "skill", "common", "敌我双方各获得 8 层灼烧，抽 2 张牌。燃尽者免疫自身灼烧伤害。消耗。", [Effect("burn", 8, "self"), Effect("burn", 8), Effect("draw", 2, "self"), Effect("exhaust_self", 1, "self")]),
    "furnace_heart": skill("furnace_heart", "熔炉心脏", 1, "power", "uncommon", "本场战斗中，敌人的灼烧每次正常结算后，力量 +4。", [Effect("burn_tick_strength", 4, "self")]),
    "fire_cycle": skill("fire_cycle", "生生之火", 1, "power", "uncommon", "每回合结束时，给敌人施加等于力量 75% 的灼烧，最低 6 层。", [Effect("end_burn_from_strength", 75, "self")]),
    "flashover": skill("flashover", "闪燃", 2, "skill", "rare", "下一次敌人正常结算灼烧时，灼烧伤害提高 100%；不额外消耗层数。", [Effect("next_burn_multiplier", 100, "self")]),
    "molten_edge": skill("molten_edge", "熔火锋刃", 1, "attack", "common", "造成 10 点伤害，并追加敌人当前灼烧 60% 的伤害；不消耗灼烧。", [Effect("damage", 10), Effect("damage_from_burn", 60)]),
    "ash_temper": skill("ash_temper", "灰烬淬体", 1, "defense", "uncommon", "获得 14 点护甲；敌人正在灼烧时，力量 +4。", [Effect("block", 14, "self"), Effect("strength_if_burning", 4, "self")]),
    "endless_fuel": skill("endless_fuel", "不熄燃料", 2, "power", "rare", "敌人灼烧每次衰减后，重新施加衰减后层数的 25%。", [Effect("burn_rekindle", 25, "self")]),
    "cinder_engine": skill("cinder_engine", "余烬引擎", 2, "power", "rare", "本场战斗每使用一张牌，给敌人施加该牌费用 x3 +2 层灼烧。", [Effect("burn_on_card", 3, "self")]),
    "solar_collapse": skill("solar_collapse", "日轮坍缩", 3, "attack", "rare", "造成 24 + 力量 4 倍的伤害；敌人灼烧不少于 25 层时再提高 50%。", [Effect("strength_finisher", 4)]),
}


UPGRADES: dict[str, Skill] = {
    "strike": skill("strike", "斩击+", 1, "attack", "basic", "造成 9 点伤害。", [Effect("damage", 9)], True),
    "defend": skill("defend", "格挡+", 1, "defense", "basic", "获得 8 点护甲。", [Effect("block", 8, "self")], True),
    "bash": skill("bash", "重击+", 2, "attack", "basic", "造成 18 点伤害。", [Effect("damage", 18)], True),
    "warcry": skill("warcry", "战意+", 1, "power", "basic", "本场战斗力量 +5。", [Effect("strength", 5, "self")], True),
    "pierce": skill("pierce", "破甲斩+", 1, "attack", "common", "造成 7 点伤害，施加 3 层易伤。", [Effect("damage", 7), Effect("vulnerable", 3)], True),
    "poison_blade": skill("poison_blade", "毒刃+", 1, "attack", "common", "造成 6 点伤害，施加 5 层中毒。", [Effect("damage", 6), Effect("poison", 5)], True),
    "quick_stab": skill("quick_stab", "迅捷刺击+", 0, "attack", "common", "造成 5 点伤害。", [Effect("damage", 5)], True),
    "double_hit": skill("double_hit", "双重打击+", 1, "attack", "common", "造成 6 点伤害 2 次。", [Effect("damage", 6, times=2)], True),
    "iron_wall": skill("iron_wall", "铁壁+", 2, "defense", "common", "获得 18 点护甲。", [Effect("block", 18, "self")], True),
    "sidestep": skill("sidestep", "闪身+", 0, "defense", "common", "获得 5 点护甲。", [Effect("block", 5, "self")], True),
    "guarded_thrust": skill("guarded_thrust", "盾刺+", 1, "attack", "common", "造成 8 点伤害，获得 8 点护甲。", [Effect("damage", 8), Effect("block", 8, "self")], True),
    "sweeping_strike": skill("sweeping_strike", "横扫+", 1, "attack", "common", "对所有敌人造成 8 点伤害。", [Effect("damage_all", 8)], True),
    "blade_storm": skill("blade_storm", "刃风+", 2, "attack", "uncommon", "对所有敌人造成 13 点伤害。", [Effect("damage_all", 13)], True),
    "agility": skill("agility", "灵巧+", 1, "power", "uncommon", "本场战斗敏捷 +5。", [Effect("dexterity", 5, "self")], True),
    "burn": skill("burn", "燃烧术+", 2, "skill", "uncommon", "施加 24 层灼烧。", [Effect("burn", 24)], True),
    "ember_cut": skill("ember_cut", "余烬斩+", 1, "attack", "common", "造成 12 点伤害，施加 12 层灼烧。", [Effect("damage", 12), Effect("burn", 12)], True),
    "flare_guard": skill("flare_guard", "火幕+", 1, "defense", "common", "获得 14 点护甲，施加 11 层灼烧。", [Effect("block", 14, "self"), Effect("burn", 11)], True),
    "inferno_seed": skill("inferno_seed", "燃核+", 2, "power", "rare", "本场战斗力量 +6，并施加 30 层灼烧。", [Effect("strength", 6, "self"), Effect("burn", 30)], True),
    "scorching_chain": skill("scorching_chain", "灼链+", 1, "skill", "uncommon", "施加 16 层灼烧和 3 层虚弱。", [Effect("burn", 16), Effect("weak", 3)], True),
    "ash_armor": skill("ash_armor", "灰烬护甲+", 2, "defense", "uncommon", "获得 26 点护甲，施加 18 层灼烧。", [Effect("block", 26, "self"), Effect("burn", 18)], True),
    "wildfire": skill("wildfire", "燎原+", 2, "skill", "rare", "施加 30 层灼烧和 3 层易伤。", [Effect("burn", 30), Effect("vulnerable", 3)], True),
    "firestorm": skill("firestorm", "火雨+", 2, "skill", "uncommon", "对所有敌人施加 18 层灼烧。", [Effect("burn_all", 18)], True),
    "poison_cloud": skill("poison_cloud", "毒雾+", 2, "skill", "uncommon", "施加 18 层中毒。", [Effect("poison", 18)], True),
    "plague_mist": skill("plague_mist", "疫雾+", 2, "skill", "uncommon", "对所有敌人施加 12 层中毒。", [Effect("poison_all", 12)], True),
    "toxic_guard": skill("toxic_guard", "毒障+", 1, "defense", "common", "获得 15 点护甲，施加 8 层中毒。", [Effect("block", 15, "self"), Effect("poison", 8)], True),
    "venom_math": skill("venom_math", "毒算+", 0, "skill", "uncommon", "施加 5 层中毒。若敌人已有中毒，额外施加 5 层。", [Effect("poison", 5), Effect("poison_if_poisoned", 5)], True),
    "septic_stab": skill("septic_stab", "腐蚀刺+", 1, "attack", "common", "造成 11 点伤害，施加 8 层中毒和 3 层易伤。", [Effect("damage", 11), Effect("poison", 8), Effect("vulnerable", 3)], True),
    "plague_wall": skill("plague_wall", "疫墙+", 2, "defense", "rare", "获得 28 点护甲。若敌人已中毒，额外施加 15 层中毒。", [Effect("block", 28, "self"), Effect("poison_if_poisoned", 15)], True),
    "weaken": skill("weaken", "虚弱打击+", 1, "attack", "common", "造成 13 点伤害，施加 4 层虚弱。", [Effect("damage", 13), Effect("weak", 4)], True),
    "focus": skill("focus", "蓄势+", 1, "power", "uncommon", "下次攻击伤害 +12。", [Effect("next_attack", 12, "self")], True),
    "guard_oath": skill("guard_oath", "坚守+", 1, "power", "rare", "本场战斗每回合开始获得 5 点护甲。", [Effect("ritual_block", 5, "self")], True),
    "hold_guard": skill("hold_guard", "固守阵线+", 1, "power", "rare", "本场战斗护甲不会在回合开始时清空。", [Effect("retain_block", 1, "self")], True),
    "blood_slash": skill("blood_slash", "饮血斩+", 1, "attack", "common", "造成 10 点伤害，按实际伤害、力量和敏捷回复生命。", [Effect("lifesteal_damage", 10)], True),
    "crimson_rush": skill("crimson_rush", "猩红突袭+", 2, "attack", "uncommon", "造成 18 点伤害，按实际伤害、力量和敏捷回复生命。", [Effect("lifesteal_damage", 18)], True),
    "blood_guard": skill("blood_guard", "血盾+", 1, "defense", "uncommon", "获得 15 点护甲，本场战斗敏捷 +5。", [Effect("block", 15, "self"), Effect("dexterity", 5, "self")], True),
    "red_harvest": skill("red_harvest", "赤色收割+", 2, "attack", "rare", "造成 13 点吸血伤害，并施加 3 层易伤。", [Effect("lifesteal_damage", 13), Effect("vulnerable", 3)], True),
    "venom_burst": skill("venom_burst", "毒爆+", 1, "skill", "uncommon", "造成敌人中毒层数 1.75 倍伤害，随后中毒变为 60%。", [Effect("poison_burst", 25)], True),
    "plague_cut": skill("plague_cut", "疫刃收割+", 2, "attack", "rare", "造成 12 点伤害，再触发强化毒爆。", [Effect("damage", 12), Effect("poison_burst", 25)], True),
    "balanced_form": skill("balanced_form", "均衡姿态+", 2, "power", "rare", "本场战斗力量 +5，敏捷 +5，获得 20 点护甲。", [Effect("strength", 5, "self"), Effect("dexterity", 5, "self"), Effect("block", 20, "self")], True),
    "execution_mark": skill("execution_mark", "处决标记+", 1, "skill", "uncommon", "施加 4 层易伤、4 层虚弱和 2 层脆弱。", [Effect("vulnerable", 4), Effect("weak", 4), Effect("fragile", 2)], True),
    "war_banner": skill("war_banner", "破阵战旗+", 2, "skill", "rare", "对所有敌人施加 3 层虚弱和 3 层易伤。", [Effect("weak_all", 3), Effect("vulnerable_all", 3)], True),
    "linebreaker": skill("linebreaker", "破线斩+", 1, "attack", "common", "对所有敌人造成 6 + 存活敌人数 x3 点伤害。", [Effect("damage_all_per_enemy", 6, times=3)], True),
    "shield_wall": skill("shield_wall", "盾墙推进+", 1, "defense", "common", "获得 9 + 存活敌人数 x4 点护甲。", [Effect("block_per_enemy", 9, "self", times=4)], True),
    "toxic_bloom": skill("toxic_bloom", "毒花绽放+", 2, "skill", "rare", "对所有敌人施加 10 层中毒，再对所有敌人触发 1.5 倍毒爆。", [Effect("poison_all", 10), Effect("poison_burst_all", 0)], True),
    "ash_surge": skill("ash_surge", "灰烬浪潮+", 2, "skill", "uncommon", "对所有敌人施加 12 层灼烧，并追加其当前灼烧 60% 的伤害。", [Effect("burn_all", 12), Effect("damage_from_burn_all", 60)], True),
    "blade_maelstrom": skill("blade_maelstrom", "乱刃风暴+", 2, "attack", "rare", "对所有敌人造成 10 点伤害 2 次。", [Effect("damage_all", 10, times=2)], True),
    "fortress_bash": skill("fortress_bash", "城塞反击+", 2, "attack", "uncommon", "获得 16 点护甲，并造成当前护甲 65% 的伤害。", [Effect("block", 16, "self"), Effect("damage_from_block", 65)], True),
    "iron_breath": skill("iron_breath", "铁壁吐息+", 2, "defense", "uncommon", "一次性获得 12 + 力量 x3 的护甲。", [Effect("block_with_strength", 12, "self", times=3)], True),
    "toxic_shell": skill("toxic_shell", "毒甲共生+", 2, "defense", "rare", "获得 16 点护甲，再获得敌人中毒层数 1.5 倍的护甲。", [Effect("block", 16, "self"), Effect("block_from_enemy_poison", 150, "self")], True),
    "flame_bastion": skill("flame_bastion", "焚城壁垒+", 3, "defense", "rare", "获得 34 点护甲，并施加 28 层灼烧。", [Effect("block", 34, "self"), Effect("burn", 28)], True),
    "power_blade": skill("power_blade", "力铸长刃+", 2, "weapon", "uncommon", "武器：造成 23 + 力量 + 敏捷伤害；本场力量 +5。", [Effect("weapon_damage", 23), Effect("strength", 5, "self")], True),
    "dancer_blades": skill("dancer_blades", "双舞短刃+", 2, "weapon", "uncommon", "武器：造成 12 + 力量 + 敏捷伤害 2 次；本场敏捷 +5。", [Effect("weapon_damage", 12, times=2), Effect("dexterity", 5, "self")], True),
    "venom_fang": skill("venom_fang", "淬毒蛇牙+", 2, "weapon", "rare", "武器：造成 21 + 力量 + 敏捷伤害，并施加 24 层中毒。", [Effect("weapon_damage", 21), Effect("poison", 24)], True),
    "cinder_greatsword": skill("cinder_greatsword", "烬火巨剑+", 3, "weapon", "rare", "武器：造成 38 + 力量 + 敏捷伤害，并施加 38 层灼烧。", [Effect("weapon_damage", 38), Effect("burn", 38)], True),
    "bulwark_hammer": skill("bulwark_hammer", "壁垒战锤+", 3, "weapon", "rare", "武器：获得 32 点护甲，造成 18 + 力量 + 敏捷伤害，再造成当前护甲 35% 的伤害。", [Effect("block", 32, "self"), Effect("weapon_damage", 18), Effect("damage_from_block", 35)], True),
    "cauterize": skill("cauterize", "炽痕引燃+", 2, "skill", "uncommon", "施加 22 层灼烧；敌人已有灼烧时额外施加其当前灼烧的 75%。", [Effect("burn", 22), Effect("burn_echo", 75)], True),
    "battle_flow": skill("battle_flow", "战术流转+", 1, "skill", "common", "抽 3 张牌。", [Effect("draw", 3, "self")], True),
    "adrenaline": skill("adrenaline", "肾上腺素+", 0, "skill", "rare", "获得 2 点能量，抽 1 张牌。消耗。", [Effect("energy", 2, "self"), Effect("draw", 1, "self"), Effect("exhaust_self", 1, "self")], True),
    "overclock": skill("overclock", "超载驱动+", 0, "skill", "uncommon", "获得 2 点能量。消耗。", [Effect("energy", 2, "self"), Effect("exhaust_self", 1, "self")], True),
    "reserve_cell": skill("reserve_cell", "储能电池+", 1, "power", "uncommon", "下回合获得 3 点额外能量并额外抽 2 张牌。", [Effect("next_energy", 3, "self"), Effect("next_draw", 2, "self")], True),
    "bloodletting": skill("bloodletting", "放血刃+", 1, "attack", "common", "造成 12 点伤害并施加 8 层流血。", [Effect("damage", 12), Effect("bleed", 8)], True),
    "fracture_hex": skill("fracture_hex", "碎甲咒+", 1, "skill", "uncommon", "施加 3 层脆弱与 2 层易伤。", [Effect("fragile", 3), Effect("vulnerable", 2)], True),
    "renewal": skill("renewal", "再生脉冲+", 1, "skill", "uncommon", "获得 10 层再生。", [Effect("regeneration", 10, "self")], True),
    "hand_detonation": skill("hand_detonation", "孤注一掷+", 2, "attack", "rare", "消耗所有手牌；造成消耗数量 x10 + 力量 + 敏捷的伤害。", [Effect("exhaust_hand_damage", 10)], True),
    "toxic_purge": skill("toxic_purge", "毒囊清仓+", 1, "skill", "rare", "消耗除本牌外的所有手牌；每消耗 1 张，施加 8 层中毒。", [Effect("exhaust_hand_poison", 8)], True),
    "ember_recycle": skill("ember_recycle", "余烬回收+", 1, "skill", "rare", "消耗除本牌外的所有手牌；每消耗 1 张，施加 10 层灼烧并获得 2 点护甲。", [Effect("exhaust_hand_burn", 10)], True),
    "opportunist": skill("opportunist", "乘隙追击+", 1, "attack", "uncommon", "造成 14 点伤害；目标处于虚弱时额外抽 3 张牌。", [Effect("damage", 14), Effect("draw_if_weak", 3, "self")], True),
    "pressure_break": skill("pressure_break", "压制破阵+", 2, "attack", "rare", "造成 24 点伤害；目标每有 1 层虚弱、易伤或脆弱，额外造成 8 点伤害。", [Effect("damage", 24), Effect("damage_per_debuff", 8)], True),
    "status_harvest": skill("status_harvest", "状态收割+", 2, "skill", "rare", "移除敌人全部虚弱、易伤和脆弱；每移除 1 层获得 1 点能量和 5 点护甲。", [Effect("consume_debuffs", 5)], True),
    "ember_breath": skill("ember_breath", "纳火吐息+", 0, "skill", "common", "敌我双方各获得 10 层灼烧，抽 3 张牌。燃尽者免疫自身灼烧伤害。消耗。", [Effect("burn", 10, "self"), Effect("burn", 10), Effect("draw", 3, "self"), Effect("exhaust_self", 1, "self")], True),
    "furnace_heart": skill("furnace_heart", "熔炉心脏+", 1, "power", "uncommon", "敌人的灼烧每次正常结算后，力量 +6。", [Effect("burn_tick_strength", 6, "self")], True),
    "fire_cycle": skill("fire_cycle", "生生之火+", 1, "power", "uncommon", "每回合结束时，给敌人施加等于力量 100% 的灼烧，最低 8 层。", [Effect("end_burn_from_strength", 100, "self")], True),
    "flashover": skill("flashover", "闪燃+", 2, "skill", "rare", "下一次敌人正常结算灼烧时，灼烧伤害提高 150%；不额外消耗层数。", [Effect("next_burn_multiplier", 150, "self")], True),
    "molten_edge": skill("molten_edge", "熔火锋刃+", 1, "attack", "common", "造成 14 点伤害，并追加敌人当前灼烧 90% 的伤害；不消耗灼烧。", [Effect("damage", 14), Effect("damage_from_burn", 90)], True),
    "ash_temper": skill("ash_temper", "灰烬淬体+", 1, "defense", "uncommon", "获得 20 点护甲；敌人正在灼烧时，力量 +6。", [Effect("block", 20, "self"), Effect("strength_if_burning", 6, "self")], True),
    "endless_fuel": skill("endless_fuel", "不熄燃料+", 2, "power", "rare", "敌人灼烧每次衰减后，重新施加衰减后层数的 40%。", [Effect("burn_rekindle", 40, "self")], True),
    "cinder_engine": skill("cinder_engine", "余烬引擎+", 2, "power", "rare", "本场战斗每使用一张牌，给敌人施加该牌费用 x4 +3 层灼烧。", [Effect("burn_on_card", 4, "self")], True),
    "solar_collapse": skill("solar_collapse", "日轮坍缩+", 3, "attack", "rare", "造成 36 + 力量 5 倍的伤害；敌人灼烧不少于 20 层时再提高 50%。", [Effect("strength_finisher", 5)], True),
}


RELICS: list[Relic] = [
    Relic("worn_charm", "磨损护符", "战斗开始时获得 5 点护甲。", "battle_start_block", 5),
    Relic("power_ring", "力量戒指", "战斗开始时力量 +1。", "battle_start_strength", 1),
    Relic("agile_feather", "灵巧羽毛", "战斗开始时敏捷 +1。", "battle_start_dexterity", 1),
    Relic("venom_bottle", "毒液瓶", "战斗开始时给敌人施加 3 层中毒。", "battle_start_poison", 3),
    Relic("war_horn", "战斗号角", "第一回合能量 +1。", "first_turn_energy", 1),
    Relic("blood_contract", "血色契约", "战斗胜利后回复 4 点生命。", "after_battle_heal", 4),
    Relic("sharpening", "锋利磨石", "攻击技能伤害 +1。", "attack_bonus", 1),
    Relic("heavy_pauldron", "厚重肩甲", "每回合第一次获得护甲时额外 +3。", "first_block_bonus", 3),
    Relic("greedy_coin", "贪婪硬币", "战斗金币奖励 +25%。", "gold_bonus", 25),
    Relic("sanguine_fang", "鲜血尖牙", "吸血类技能额外回复 3 点生命。", "lifesteal_bonus", 3),
    Relic("plague_lens", "瘟疫透镜", "毒爆伤害倍率额外 +25%。", "poison_burst_bonus", 25),
    Relic("leech_core", "汲血核心", "战斗开始时力量和敏捷各 +1。", "battle_start_blood_stats", 1),
    Relic("toxic_abacus", "毒算算盘", "诡毒师被动施加的中毒额外 +1。", "toxic_passive_bonus", 1),
    Relic("cinder_crown", "余烬冠", "燃尽者每回合由灼烧转化的力量额外 +1。", "burn_strength_bonus", 1),
    Relic("adaptive_badge", "适应徽记", "流亡者每场战斗开始额外获得 +1 力量和 +1 敏捷。", "exile_start_bonus", 1),
    Relic("iron_seed", "铁种子", "战斗开始时获得 10 点护甲。", "battle_start_block", 10),
    Relic("red_whetstone", "赤红磨石", "攻击技能伤害 +2。", "attack_bonus", 2),
    Relic("night_needle", "夜针", "战斗开始时给敌人施加 5 层中毒。", "battle_start_poison", 5),
    Relic("old_banner", "旧战旗", "战斗开始时力量 +2。", "battle_start_strength", 2),
    Relic("glass_feather", "玻璃羽", "战斗开始时敏捷 +2。", "battle_start_dexterity", 2),
    Relic("war_drum", "战鼓", "第一回合能量 +2。", "first_turn_energy", 2),
    Relic("deep_vein", "深红血脉", "吸血类技能额外回复 5 点生命。", "lifesteal_bonus", 5),
    Relic("black_cauldron", "黑釜", "毒爆伤害倍率额外 +50%。", "poison_burst_bonus", 50),
    Relic("ashen_diadem", "灰烬冕", "燃尽者每回合由灼烧转化的力量额外 +2。", "burn_strength_bonus", 2),
    Relic("adaptive_core", "适应核心", "流亡者每场战斗开始额外获得 +2 力量和 +2 敏捷。", "exile_start_bonus", 2),
    Relic("weapon_core", "兵装核心", "武器牌伤害 +4。", "weapon_bonus", 4),
    Relic("status_forge", "蚀焰锻炉", "武器牌命中中毒或灼烧目标时伤害 +5。", "status_weapon_bonus", 5),
    Relic("toxic_plating", "毒素镀层", "根据敌人中毒获得护甲时，额外获得 4 点护甲。", "poison_block_bonus", 4),
    Relic("ember_shield", "余火盾芯", "战斗开始施加 6 层灼烧并获得 8 点护甲。", "battle_start_burn_block", 6),
    Relic("fortress_spring", "壁垒发条", "每回合第一次获得护甲时额外 +6。", "first_block_bonus", 6),
    Relic("baiye_fragment", "白夜碎片", "战斗开始时力量与敏捷各 +2，并获得 12 点护甲。", "battle_start_trinity", 2),
    Relic("folded_hourglass", "折叠沙漏", "第一回合额外抽 2 张牌。", "first_turn_draw", 2),
    Relic("waste_heat", "废热回收器", "每消耗 1 张牌，获得 3 点护甲。", "exhaust_block", 3),
    Relic("renewal_seed", "再生种子", "战斗开始时获得 6 层再生。", "battle_start_regeneration", 6),
    Relic("cleave_charm", "裂阵护符", "全体伤害牌的基础伤害 +2。只影响写明“所有敌人/全体伤害”的卡。", "group_damage_bonus", 2),
    Relic("echo_banner", "回声战旗", "每使用 1 张群体牌，获得 5 点护甲。群体牌包含全体伤害、全体中毒、全体灼烧和全体负面。", "group_card_block", 5),
    Relic("splinter_blade", "裂刃碎片", "用攻击牌击杀敌人时，对其余所有敌人造成 8 点溅射伤害。", "overkill_splash", 8),
    Relic("ash_urn", "灰烬坛", "战斗开始时对所有敌人施加 8 层灼烧。", "battle_start_burn", 8),
    Relic("plague_bell", "疫病铃", "战斗开始时对所有敌人施加 7 层中毒。", "battle_start_poison", 7),
]


def upgrade_skill(base: Skill) -> Skill:
    if base.upgrade_level >= 2:
        return base
    if base.upgrade_level == 0:
        upgraded = UPGRADES.get(base.id, base)
    else:
        upgraded = second_upgrade(base)
    return _apply_upgrade_cost(base, upgraded)


def _apply_upgrade_cost(base: Skill, upgraded: Skill) -> Skill:
    reduce_first_upgrade = base.upgrade_level == 0 and base.cost >= 2
    reduce_special_second = base.id == "battle_flow" and upgraded.upgrade_level == 2
    if (not reduce_first_upgrade and not reduce_special_second) or upgraded is base:
        return upgraded
    new_cost = min(upgraded.cost, base.cost - 1)
    return Skill(upgraded.id, upgraded.name, new_cost, upgraded.category, upgraded.rarity,
                 upgraded.description, upgraded.effects, upgraded.upgraded, upgraded.upgrade_level)


def second_upgrade(base: Skill) -> Skill:
    if base.id == "iron_breath":
        return Skill(base.id, "铁壁吐息++", base.cost, base.category, base.rarity,
                     "一次性获得 16 + 力量 x4 的护甲。",
                     (Effect("block_with_strength", 16, "self", times=4),), True, 2)
    if base.id == "battle_flow":
        return Skill(base.id, "战术流转++", base.cost, base.category, base.rarity,
                     "抽 3 张牌，费用降为 0。", base.effects, True, 2)
    if base.id == "adrenaline":
        return Skill(base.id, "肾上腺素++", base.cost, base.category, base.rarity,
                     "获得 2 点能量，抽 2 张牌。消耗。",
                     (Effect("energy", 2, "self"), Effect("draw", 2, "self"), Effect("exhaust_self", 1, "self")), True, 2)
    if base.id == "overclock":
        return Skill(base.id, "超载驱动++", base.cost, base.category, base.rarity,
                     "获得 2 点能量并抽 1 张牌。消耗。",
                     (Effect("energy", 2, "self"), Effect("draw", 1, "self"), Effect("exhaust_self", 1, "self")), True, 2)
    effects = tuple(_upgrade_effect(effect) for effect in base.effects)
    if base.id == "hold_guard":
        effects = effects + (Effect("block", 10, "self"),)
    name = base.name if base.name.endswith("++") else base.name.rstrip("+") + "++"
    description = base.description + " 二次升级：数值进一步提高。"
    return Skill(base.id, name, base.cost, base.category, base.rarity, description, effects, True, 2)


def _upgrade_effect(effect: Effect) -> Effect:
    scalable = {
        "damage",
        "damage_all",
        "damage_all_per_enemy",
        "lifesteal_damage",
        "block",
        "block_per_enemy",
        "vulnerable",
        "vulnerable_all",
        "weak",
        "weak_all",
        "poison",
        "poison_all",
        "burn",
        "burn_all",
        "strength",
        "dexterity",
        "ritual_block",
        "next_attack",
        "poison_if_poisoned",
        "poison_burst",
        "poison_burst_all",
        "weapon_damage",
        "damage_from_block",
        "block_from_strength",
        "block_with_strength",
        "block_from_enemy_poison",
        "burn_echo",
        "draw",
        "energy",
        "next_energy",
        "next_draw",
        "bleed",
        "fragile",
        "regeneration",
        "exhaust_hand_damage",
        "exhaust_hand_poison",
        "exhaust_hand_burn",
        "damage_per_debuff",
        "consume_debuffs",
        "burn_tick_strength",
        "end_burn_from_strength",
        "next_burn_multiplier",
        "damage_from_burn",
        "damage_from_burn_all",
        "strength_if_burning",
        "burn_rekindle",
        "burn_on_card",
        "strength_finisher",
    }
    if effect.kind not in scalable:
        return effect
    increase = max(1, (abs(effect.value) + 1) // 2)
    return Effect(effect.kind, effect.value + increase, effect.target, effect.times)


def starting_player() -> Player:
    return create_player("exile")


def create_player(role_id: str) -> Player:
    if role_id == "toxicist":
        deck = [
            SKILLS["strike"],
            SKILLS["defend"],
            SKILLS["defend"],
            SKILLS["poison_blade"],
            SKILLS["poison_cloud"],
            SKILLS["venom_burst"],
            SKILLS["toxic_guard"],
            SKILLS["venom_math"],
        ]
        return Player(role_id="toxicist", name="诡毒师", max_hp=94, hp=94, energy_max=4, energy=4, gold=199, skills=deck)
    if role_id == "burner":
        deck = [
            SKILLS["strike"],
            SKILLS["defend"],
            SKILLS["defend"],
            SKILLS["ember_cut"],
            SKILLS["flare_guard"],
            SKILLS["burn"],
            SKILLS["wildfire"],
            SKILLS["inferno_seed"],
            SKILLS["furnace_heart"],
            SKILLS["molten_edge"],
        ]
        return Player(role_id="burner", name="燃尽者", max_hp=98, hp=98, energy_max=4, energy=4, gold=199, skills=deck)
    deck = [
        SKILLS["strike"],
        SKILLS["strike"],
        SKILLS["strike"],
        SKILLS["defend"],
        SKILLS["defend"],
        SKILLS["defend"],
        SKILLS["bash"],
        SKILLS["warcry"],
    ]
    return Player(role_id="exile", name="流亡者", max_hp=100, hp=100, starter_bonus=2, energy_max=4, energy=4, gold=199, skills=deck)


def move(name: str, intent: str, effects: list[Effect]) -> EnemyMove:
    return EnemyMove(name, intent, tuple(effects))


def normal_enemy(act: int) -> Enemy:
    pool = [
        Enemy("裂爪兽", 38 + act * 8, 38 + act * 8, mechanics={"pack_hunter": 2 + act}, moves=[
            move("撕咬", "攻击 8", [Effect("damage", 8 + act * 2)]),
            move("利爪", "攻击 5，虚弱 1", [Effect("damage", 5 + act), Effect("weak", 1)]),
            move("低吼", "获得 6 护甲", [Effect("block", 6 + act * 2, "self")]),
        ]),
        Enemy("铁甲虫", 45 + act * 10, 45 + act * 10, mechanics={"shell_guard": 6 + act * 2, "thorn": 2 + act}, moves=[
            move("撞击", "攻击 7", [Effect("damage", 7 + act * 2)]),
            move("甲壳收缩", "获得 12 护甲", [Effect("block", 12 + act * 2, "self")]),
            move("重撞", "攻击 12", [Effect("damage", 12 + act * 2)]),
        ]),
        Enemy("毒囊怪", 32 + act * 9, 32 + act * 9, mechanics={"death_poison": 3 + act}, moves=[
            move("毒液", "中毒 4", [Effect("poison", 4 + act)]),
            move("啃咬", "攻击 6", [Effect("damage", 6 + act * 2)]),
            move("毒咬", "攻击 4，中毒 2", [Effect("damage", 4 + act), Effect("poison", 2 + act)]),
        ]),
    ]
    enemy = random.choice(pool)
    return _enrage_enemy(enemy) if act == 4 else enemy


def elite_enemy(act: int) -> Enemy:
    pool = [
        Enemy("双头守卫", 85 + act * 16, 85 + act * 16, mechanics={"rally_block": 4 + act * 2}, moves=[
            move("双重劈砍", "攻击 8 x2", [Effect("damage", 8 + act * 2, times=2)]),
            move("守势", "获得 12 护甲", [Effect("block", 12 + act * 3, "self")]),
            move("粉碎", "攻击 10，易伤 2", [Effect("damage", 10 + act * 2), Effect("vulnerable", 2)]),
        ]),
        Enemy("尖刺傀儡", 75 + act * 18, 75 + act * 18, thorn_damage=3 + act, mechanics={"shell_guard": 10 + act * 2, "thorn": 3 + act}, moves=[
            move("架刺", "获得 15 护甲", [Effect("block", 15 + act * 3, "self")]),
            move("铁拳", "攻击 10", [Effect("damage", 10 + act * 3)]),
            move("连锤", "攻击 6 x2", [Effect("damage", 6 + act * 2, times=2)]),
        ]),
    ]
    enemy = random.choice(pool)
    return _enrage_enemy(enemy) if act == 4 else enemy


def _enrage_enemy(enemy: Enemy) -> Enemy:
    enemy.name = f"狂暴·{enemy.name}"
    enemy.max_hp = math.ceil(enemy.max_hp * 1.8)
    enemy.hp = enemy.max_hp
    enemy.strength = math.ceil(max(1, enemy.strength + 4) * 1.8)
    enemy.block = math.ceil(20 * 1.8)
    enemy.enraged = True
    return enemy


def boss_enemy(act: int) -> Enemy:
    if act == 1:
        return Enemy("熔炉骑士", 150, 150, moves=[
            move("斩击", "攻击 12", [Effect("damage", 12)]),
            move("举盾", "获得 15 护甲", [Effect("block", 15, "self")]),
            move("蓄力", "下回合重击", [Effect("strength", 2, "self")]),
            move("熔炉重击", "攻击 32", [Effect("damage", 32)]),
        ])
    if act == 2:
        return Enemy("瘟疫主教", 190, 190, moves=[
            move("瘟疫", "中毒 5", [Effect("poison", 5)]),
            move("权杖", "攻击 13", [Effect("damage", 13)]),
            move("腐化祷言", "攻击 8，虚弱 2", [Effect("damage", 8), Effect("weak", 2)]),
            move("毒潮", "中毒 4，攻击 10", [Effect("poison", 4), Effect("damage", 10)]),
        ])
    if act == 3:
        return Enemy("塔心化身", 260, 260, moves=[
        move("心跳", "攻击 16", [Effect("damage", 16)]),
        move("适应", "力量 +2，获得 10 护甲", [Effect("strength", 2, "self"), Effect("block", 10, "self")]),
        move("脉冲", "攻击 8 x3", [Effect("damage", 8, times=3)]),
        move("净化", "获得 18 护甲", [Effect("block", 18, "self")]),
        ])
    return Enemy("Baiye", 2499, 2499, strength=5, dexterity=5, boss_id="baiye", moves=[
        move("随机兵装", "获得 3 张随机等级卡牌，并随机打出 1-3 张", []),
    ])


def enemy_group(enemy_type: str, act: int, floor_in_act: int) -> list[Enemy]:
    if enemy_type == "boss":
        return [boss_enemy(act)]
    if enemy_type == "elite":
        count = 1 if floor_in_act <= 1 else random.randint(1, 2)
        return [elite_enemy(act) for _ in range(count)]
    count = 1 if floor_in_act <= 1 else random.randint(1, 3)
    return [normal_enemy(act) for _ in range(count)]


def reward_skills(count: int = 3) -> list[Skill]:
    candidates = [s for s in SKILLS.values() if s.rarity != "basic"]
    return random.sample(candidates, min(count, len(candidates)))


def shop_skill_offers(count: int = 3, upgraded_chance: float = 0.35) -> list[Skill]:
    offers = reward_skills()
    while len(offers) < count:
        offers.extend(reward_skills())
    offers = offers[:count]
    return [
        upgrade_skill(skill) if random.random() < upgraded_chance else skill
        for skill in offers
    ]


ROLE_RELIC_HOOKS = {
    "toxic_passive_bonus": "toxicist",
    "burn_strength_bonus": "burner",
    "exile_start_bonus": "exile",
}


def relic_available_for_role(relic: Relic, role_id: str) -> bool:
    required_role = ROLE_RELIC_HOOKS.get(relic.hook)
    return required_role is None or required_role == role_id


def random_relics(excluding: list[Relic], role_id: str, count: int) -> list[Relic]:
    owned = {r.id for r in excluding}
    choices = [r for r in RELICS if r.id not in owned and relic_available_for_role(r, role_id)]
    return random.sample(choices, min(count, len(choices)))


def random_relic(excluding: list[Relic], role_id: str) -> Relic | None:
    choices = random_relics(excluding, role_id, 1)
    return choices[0] if choices else None
