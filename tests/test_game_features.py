import math
import random
import unittest
from unittest.mock import patch

from game.combat import Combat
from game.ai_adapter import RogueGameAdapter
from game.catalog import card_catalog_entries, relic_catalog_entries
from game.data import RELICS, SKILLS, boss_enemy, create_player, normal_enemy, random_relics, upgrade_skill
from game.runner import Game


class ChapterFourTests(unittest.TestCase):
    def test_chapter_four_enemy_is_enraged(self) -> None:
        random.seed(1)
        enemy = normal_enemy(4)
        self.assertTrue(enemy.enraged)
        self.assertTrue(enemy.name.startswith("狂暴·"))
        self.assertEqual(enemy.block, 36)
        self.assertEqual(enemy.strength, 8)

    def test_baiye_base_stats(self) -> None:
        enemy = boss_enemy(4)
        self.assertEqual((enemy.name, enemy.hp, enemy.max_hp), ("Baiye", 2499, 2499))
        self.assertEqual((enemy.strength, enemy.dexterity), (5, 5))
        self.assertEqual(enemy.boss_id, "baiye")


class UpgradeTests(unittest.TestCase):
    def test_high_cost_card_only_reduces_cost_on_designed_upgrade(self) -> None:
        card = SKILLS["cinder_greatsword"]
        first = upgrade_skill(card)
        second = upgrade_skill(first)
        self.assertEqual((card.cost, first.cost, second.cost), (3, 2, 2))
        self.assertEqual(second.upgrade_level, 2)

    def test_every_high_cost_card_first_upgrade_reduces_cost(self) -> None:
        high_cost_cards = [card for card in SKILLS.values() if card.cost >= 2]
        for card in high_cost_cards:
            self.assertEqual(upgrade_skill(card).cost, card.cost - 1, card.id)

    def test_upgrade_can_change_mechanism_instead_of_numbers(self) -> None:
        overclock = upgrade_skill(upgrade_skill(SKILLS["overclock"]))
        kinds = [effect.kind for effect in overclock.effects]
        self.assertIn("draw", kinds)
        self.assertNotIn("energy_debt", kinds)

        battle_flow = upgrade_skill(upgrade_skill(SKILLS["battle_flow"]))
        self.assertEqual((battle_flow.cost, battle_flow.effects[0].value), (0, 3))


class ExileGrowthTests(unittest.TestCase):
    def test_growth_is_stronger_but_does_not_include_temporary_stats(self) -> None:
        game = Game()
        game.player = create_player("exile")
        game.player.starter_bonus = 20
        game.player.strength = 999
        game.player.dexterity = 888
        game._after_floor_clear()
        self.assertEqual(game.player.starter_bonus, 24)
        self.assertEqual((game.player.strength, game.player.dexterity), (0, 0))

    def test_growth_cap_is_80(self) -> None:
        game = Game()
        game.player = create_player("exile")
        game.player.starter_bonus = 79
        game._after_floor_clear()
        self.assertEqual(game.player.starter_bonus, 80)

    def test_exile_adaptation_adds_strength_and_dexterity(self) -> None:
        player = create_player("exile")
        combat = Combat(player, normal_enemy(1))
        combat._battle_start()
        self.assertEqual((player.strength, player.dexterity), (2, 2))


class WebPreviewTests(unittest.TestCase):
    def test_hand_card_preview_uses_current_strength(self) -> None:
        adapter = RogueGameAdapter("exile", seed=1)
        adapter.start_combat("normal")
        assert adapter.combat is not None
        adapter.player.strength = 10
        adapter.combat.hand = [SKILLS["strike"]]

        card = adapter.get_state()["combat"]["hand"][0]

        self.assertIn("造成 6 点伤害", card["description"])
        self.assertEqual(card["preview"], "伤害 16")


class StartingResourceTests(unittest.TestCase):
    def test_role_menu_can_select_burner(self) -> None:
        game = Game()
        with patch("builtins.input", return_value="3"):
            game._choose_role()
        self.assertEqual(game.player.role_id, "burner")
        self.assertEqual(game.player.name, "燃尽者")

    def test_all_roles_gain_30_hp_and_100_gold(self) -> None:
        expected_hp = {"exile": 100, "toxicist": 94, "burner": 98}
        for role_id, hp in expected_hp.items():
            player = create_player(role_id)
            self.assertEqual((player.hp, player.max_hp, player.gold), (hp, hp, 199))

    def test_role_relics_only_appear_for_matching_role(self) -> None:
        exclusive_hooks = {
            "exile": "exile_start_bonus",
            "toxicist": "toxic_passive_bonus",
            "burner": "burn_strength_bonus",
        }
        for role_id, allowed_hook in exclusive_hooks.items():
            offers = random_relics([], role_id, len(RELICS))
            offered_hooks = {relic.hook for relic in offers}
            self.assertIn(allowed_hook, offered_hooks)
            for other_hook in set(exclusive_hooks.values()) - {allowed_hook}:
                self.assertNotIn(other_hook, offered_hooks)

    def test_shop_can_offer_four_unique_relics(self) -> None:
        offers = random_relics([], "exile", 4)
        self.assertEqual(len(offers), 4)
        self.assertEqual(len({relic.id for relic in offers}), 4)


class CatalogTests(unittest.TestCase):
    def test_catalog_contains_every_card_and_relic(self) -> None:
        self.assertEqual(len(card_catalog_entries()), len(SKILLS))
        self.assertEqual(len(relic_catalog_entries()), len(RELICS))

    def test_card_catalog_shows_all_upgrade_levels(self) -> None:
        entry = next(entry for entry in card_catalog_entries() if "超载驱动" in entry)
        self.assertIn("Lv.0", entry)
        self.assertIn("Lv.1", entry)
        self.assertIn("Lv.2", entry)
        self.assertIn("抽 1 张牌", entry)

    def test_relic_catalog_marks_role_exclusivity(self) -> None:
        entries = relic_catalog_entries()
        self.assertTrue(any("适应徽记" in entry and "流亡者专属" in entry for entry in entries))
        self.assertTrue(any("毒算算盘" in entry and "诡毒师专属" in entry for entry in entries))
        self.assertTrue(any("余烬冠" in entry and "燃尽者专属" in entry for entry in entries))


class BaiyeCombatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.player = create_player("exile")
        self.enemy = boss_enemy(4)
        self.combat = Combat(self.player, self.enemy)

    def test_each_hp_loss_instance_grants_one_strength_and_dexterity(self) -> None:
        self.combat._deal_damage(self.player, self.enemy, 10, SKILLS["strike"])
        self.assertEqual((self.enemy.strength, self.enemy.dexterity), (6, 6))
        self.combat._deal_direct_hp_loss(self.enemy, 5, "测试")
        self.assertEqual((self.enemy.strength, self.enemy.dexterity), (7, 7))

    def test_heals_every_two_turns_below_threshold(self) -> None:
        self.enemy.hp = 900
        self.combat._advance_baiye_healing()
        self.assertEqual(self.enemy.hp, 900)
        self.combat._advance_baiye_healing()
        self.assertEqual(self.enemy.hp, 900 + math.ceil(2499 * 0.2))

    def test_shield_releases_remaining_block_after_three_turns(self) -> None:
        self.enemy.block = 200
        self.combat.baiye_shield_turns = 3
        start_hp = self.player.hp
        self.combat._advance_baiye_shield()
        self.combat._advance_baiye_shield()
        self.assertEqual(self.player.hp, start_hp)
        self.combat._advance_baiye_shield()
        self.assertEqual(self.player.hp, 0)
        self.assertEqual(self.enemy.block, 0)

    def test_baiye_prepares_three_random_level_cards(self) -> None:
        random.seed(3)
        self.combat._prepare_baiye_hand()
        self.assertEqual(len(self.combat.baiye_hand), 3)
        self.assertTrue(all(0 <= card.upgrade_level <= 2 for card in self.combat.baiye_hand))
        self.assertIn("Lv.", self.enemy.current_move.intent)


class SynergyTests(unittest.TestCase):
    def test_burner_iron_breath_applies_strength_block_at_all_levels(self) -> None:
        expected = [(0, 48), (1, 72), (2, 96)]
        card = SKILLS["iron_breath"]
        for level, expected_block in expected:
            player = create_player("burner")
            player.strength = 20
            player.energy = 4
            combat = Combat(player, normal_enemy(1))
            combat._use_skill(card)
            self.assertEqual(player.block, expected_block, f"Lv.{level}")
            if level < 2:
                card = upgrade_skill(card)

    def test_weapon_scales_with_strength_and_dexterity(self) -> None:
        player = create_player("exile")
        enemy = normal_enemy(1)
        enemy.max_hp = 500
        enemy.hp = 500
        enemy.block = 0
        player.strength = 3
        player.dexterity = 4
        combat = Combat(player, enemy)
        start_hp = enemy.hp
        combat._apply_effect(player, enemy, SKILLS["power_blade"].effects[0], SKILLS["power_blade"])
        self.assertEqual(start_hp - enemy.hp, 16 + 3 + 4)

    def test_multi_hit_weapon_applies_both_stats_to_each_hit(self) -> None:
        player = create_player("exile")
        enemy = normal_enemy(1)
        enemy.block = 0
        player.strength = 2
        player.dexterity = 3
        combat = Combat(player, enemy)
        start_hp = enemy.hp
        combat._apply_effect(player, enemy, SKILLS["dancer_blades"].effects[0], SKILLS["dancer_blades"])
        self.assertEqual(start_hp - enemy.hp, (8 + 2 + 3) * 2)

    def test_toxicist_passive_uses_actual_weapon_damage(self) -> None:
        player = create_player("toxicist")
        player.strength = 4
        player.dexterity = 3
        enemy = normal_enemy(1)
        enemy.block = 0
        combat = Combat(player, enemy)
        player.energy = 4
        combat._use_skill(SKILLS["power_blade"])
        self.assertGreaterEqual(enemy.statuses.get("poison", 0), (16 + 4 + 3) // 3)

    def test_burner_converts_each_three_burn_to_strength(self) -> None:
        player = create_player("burner")
        combat = Combat(player, normal_enemy(1))
        combat.player_burn_applied_this_turn = 21
        combat._apply_burner_passive()
        self.assertEqual(player.strength, 7)

    def test_burner_is_immune_to_burn_but_burn_still_decays(self) -> None:
        player = create_player("burner")
        combat = Combat(player, normal_enemy(1))
        player.block = 0
        player.statuses["burn"] = 20
        start_hp = player.hp
        combat._tick_burn(player)
        self.assertEqual(player.hp, start_hp)
        self.assertEqual(player.statuses["burn"], 10)

    def test_ember_breath_applies_burn_to_both_sides(self) -> None:
        player = create_player("burner")
        enemy = normal_enemy(1)
        combat = Combat(player, enemy)

        combat._use_skill(SKILLS["ember_breath"])

        self.assertEqual(player.statuses.get("burn"), 8)
        self.assertEqual(enemy.statuses.get("burn"), 8)
        self.assertEqual(combat.player_burn_applied_this_turn, 8)

    def test_flashover_amplifies_next_normal_burn_tick_without_extra_decay(self) -> None:
        player = create_player("burner")
        enemy = normal_enemy(1)
        enemy.max_hp = 500
        enemy.hp = 500
        enemy.block = 0
        combat = Combat(player, enemy)
        player.turn_powers["next_burn_multiplier"] = 100
        enemy.statuses["burn"] = 20
        combat._tick_burn(enemy)
        self.assertEqual(enemy.hp, 460)
        self.assertEqual(enemy.statuses["burn"], 10)
        self.assertNotIn("next_burn_multiplier", player.turn_powers)

    def test_furnace_heart_grows_strength_on_burn_settlement(self) -> None:
        player = create_player("burner")
        enemy = normal_enemy(1)
        combat = Combat(player, enemy)
        player.turn_powers["burn_tick_strength"] = 4
        enemy.statuses["burn"] = 8
        combat._tick_burn(enemy)
        self.assertEqual(player.strength, 4)

    def test_solar_collapse_scales_with_strength_and_burn_threshold(self) -> None:
        player = create_player("burner")
        enemy = normal_enemy(1)
        enemy.max_hp = 1000
        enemy.hp = 1000
        enemy.block = 0
        combat = Combat(player, enemy)
        player.strength = 20
        enemy.statuses["burn"] = 30
        combat._apply_effect(player, enemy, SKILLS["solar_collapse"].effects[0], SKILLS["solar_collapse"])
        self.assertEqual(enemy.hp, 1000 - math.floor((24 + 20 * 4) * 1.5))


class ResourceMechanicTests(unittest.TestCase):
    def test_draw_adds_cards_without_exceeding_hand_limit(self) -> None:
        player = create_player("exile")
        player.skills.extend([SKILLS["battle_flow"], SKILLS["adrenaline"], SKILLS["bloodletting"]])
        combat = Combat(player, normal_enemy(1))
        combat.hand = [SKILLS["battle_flow"]]
        combat._draw_cards(20)
        self.assertLessEqual(len(combat.hand), 10)
        self.assertGreater(len(combat.hand), 1)

    def test_exhaust_hand_damage_counts_self_and_removes_other_cards(self) -> None:
        player = create_player("exile")
        enemy = normal_enemy(1)
        enemy.block = 0
        combat = Combat(player, enemy)
        card = SKILLS["hand_detonation"]
        combat.hand = [card, SKILLS["strike"], SKILLS["defend"]]
        player.energy = 4
        start_hp = enemy.hp
        combat._use_skill(card)
        self.assertEqual(start_hp - enemy.hp, 21)
        self.assertEqual(combat.hand, [card])
        self.assertEqual(sum(combat.exhausted_cards.values()), 3)

    def test_exhaust_hand_damage_scales_once_with_strength_and_dexterity(self) -> None:
        player = create_player("exile")
        enemy = normal_enemy(1)
        enemy.max_hp = 500
        enemy.hp = 500
        enemy.block = 0
        combat = Combat(player, enemy)
        card = SKILLS["hand_detonation"]
        combat.hand = [card, SKILLS["strike"], SKILLS["defend"]]
        player.strength = 20
        player.dexterity = 15
        player.energy = 4
        start_hp = enemy.hp
        combat._use_skill(card)
        self.assertEqual(start_hp - enemy.hp, 3 * 7 + 20 + 15)

    def test_fragile_reduces_block_and_regeneration_heals(self) -> None:
        player = create_player("exile")
        combat = Combat(player, normal_enemy(1))
        player.statuses["fragile"] = 2
        combat._gain_block(player, 12, add_dexterity=False)
        self.assertEqual(player.block, 9)
        player.hp -= 20
        player.statuses["regeneration"] = 6
        combat._tick_regeneration(player)
        self.assertEqual(player.hp, player.max_hp - 14)
        self.assertEqual(player.statuses["regeneration"], 5)

    def test_overclock_records_next_turn_energy_debt(self) -> None:
        player = create_player("exile")
        combat = Combat(player, normal_enemy(1))
        player.energy = 0
        for effect in SKILLS["overclock"].effects:
            combat._apply_effect(player, combat.ctx.enemy, effect, SKILLS["overclock"])
        self.assertEqual(player.energy, 2)
        self.assertEqual(player.turn_powers.get("energy_debt"), 1)

    def test_upgraded_ember_recycle_gains_two_block_per_card(self) -> None:
        player = create_player("burner")
        combat = Combat(player, normal_enemy(1))
        card = upgrade_skill(SKILLS["ember_recycle"])
        combat.hand = [card, SKILLS["strike"], SKILLS["defend"]]
        combat._apply_effect(player, combat.ctx.enemy, card.effects[0], card)
        self.assertEqual(player.block, 4)

    def test_armor_blocks_poison_and_burn_but_not_bleed(self) -> None:
        player = create_player("exile")
        combat = Combat(player, normal_enemy(1))
        player.block = 20
        player.statuses.update({"poison": 8, "burn": 6, "bleed": 5})
        start_hp = player.hp
        combat._tick_poison(player)
        combat._tick_burn(player)
        self.assertEqual((player.hp, player.block), (start_hp, 6))
        combat._tick_bleed(player)
        self.assertEqual((player.hp, player.block), (start_hp - 5, 6))

    def test_start_of_turn_poison_uses_previous_turn_block_before_reset(self) -> None:
        player = create_player("exile")
        combat = Combat(player, normal_enemy(1))
        combat.ctx.turn = 1
        player.block = 10
        player.statuses["poison"] = 8
        combat._tick_regeneration(player)
        combat._tick_poison(player)
        if combat.ctx.turn > 1 and not player.turn_powers.get("retain_block", 0):
            player.block = 0
        self.assertEqual(player.hp, player.max_hp)
        self.assertEqual(player.block, 2)

    def test_reserve_cell_keeps_player_turn_running(self) -> None:
        player = create_player("exile")
        enemy = normal_enemy(1)
        combat = Combat(player, enemy)
        enemy.select_next_move()
        hand = [SKILLS["reserve_cell"], SKILLS["strike"], SKILLS["defend"]]
        with patch("game.combat.choose_many", return_value=list(hand)), \
                patch("game.combat.clear_screen"), \
                patch("builtins.input", side_effect=["1", "end"]):
            combat._player_turn()
        self.assertEqual(player.turn_powers.get("next_energy"), 2)
        self.assertEqual(player.turn_powers.get("next_draw"), 1)
        self.assertEqual(len(combat.hand), 2)

    def test_debuff_synergy_can_draw_and_convert_layers(self) -> None:
        player = create_player("exile")
        enemy = normal_enemy(1)
        combat = Combat(player, enemy)
        combat.hand = [SKILLS["opportunist"]]
        enemy.statuses.update({"weak": 2, "vulnerable": 1, "fragile": 1})
        combat._apply_effect(player, enemy, SKILLS["opportunist"].effects[1], SKILLS["opportunist"])
        self.assertGreater(len(combat.hand), 1)
        player.energy = 0
        combat._apply_effect(player, enemy, SKILLS["status_harvest"].effects[0], SKILLS["status_harvest"])
        self.assertEqual(player.energy, 4)
        self.assertEqual(player.block, 12)
        self.assertFalse(any(status in enemy.statuses for status in ("weak", "vulnerable", "fragile")))


class DeckBuildingTests(unittest.TestCase):
    def test_card_removal_removes_selected_copy(self) -> None:
        game = Game()
        original_count = len(game.player.skills)
        with patch("builtins.input", return_value="1"):
            removed = game._choose_card_removal()
        self.assertIsNotNone(removed)
        self.assertEqual(len(game.player.skills), original_count - 1)


if __name__ == "__main__":
    unittest.main()
