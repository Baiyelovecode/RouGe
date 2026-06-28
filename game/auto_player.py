from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
from typing import Any

from game.ai_adapter import RogueGameAdapter
from game.llm_agent import LLMRogueAgent


@dataclass
class AutoRunResult:
    role_id: str
    seed: int | None
    combats_requested: int
    combats_finished: int = 0
    wins: int = 0
    losses: int = 0
    actions: int = 0
    final_state: dict[str, Any] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)


class HeuristicRogueAgent:
    """
    第一版自动玩家。

    只通过 RogueGameAdapter 暴露的接口决策，不读取/修改内部 Combat 对象。
    """

    def choose_action(
        self,
        state: dict[str, Any],
        legal_actions: list[dict[str, Any]],
    ) -> tuple[str, dict[str, Any], str]:
        if state.get("phase") != "combat":
            return "start_combat", {"enemy_type": "normal"}, "不在战斗中，开始普通战斗"

        playable = [
            action for action in legal_actions
            if action.get("action") == "play_card" and action.get("legal")
        ]
        if not playable:
            return "end_turn", {}, "没有可用手牌，结束回合"

        combat = state.get("combat", {})
        player = state.get("player", {})
        enemy = combat.get("enemy", {})
        enemy_intent = str(enemy.get("intent", ""))
        incoming_damage = self._estimate_incoming_damage(enemy.get("current_move"))
        current_block = int(player.get("block", 0))
        need_block = max(0, incoming_damage - current_block)

        scored = [
            (self._score_play(action, enemy, need_block), action)
            for action in playable
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, best = scored[0]
        card = best.get("card", {})
        reason = (
            f"选择 {card.get('name', 'unknown')}，score={best_score}; "
            f"敌人意图={enemy_intent or '未知'}，预计来伤={incoming_damage}，需补护甲={need_block}"
        )
        return "play_card", dict(best.get("params", {})), reason

    def _score_play(
        self,
        action: dict[str, Any],
        enemy: dict[str, Any],
        need_block: int,
    ) -> int:
        card = action.get("card", {})
        effects = card.get("effects", [])
        score = 0
        enemy_hp = int(enemy.get("hp", 0))
        enemy_block = int(enemy.get("block", 0))
        enemy_poison = int(enemy.get("statuses", {}).get("poison", 0))

        for effect in effects:
            kind = effect.get("kind")
            value = int(effect.get("value", 0))
            times = int(effect.get("times", 1))
            target = effect.get("target", "enemy")
            if kind in {"damage", "lifesteal_damage"}:
                damage = max(0, value * times - enemy_block)
                score += damage * 3
                if damage >= enemy_hp:
                    score += 1000
                if kind == "lifesteal_damage":
                    score += max(2, damage // 2)
            elif kind == "block" and target == "self":
                block_value = value * times
                score += min(block_value, need_block) * 4
                score += max(0, block_value - need_block)
            elif kind in {"vulnerable", "weak", "poison", "burn"}:
                score += value * 4
            elif kind == "poison_burst":
                score += enemy_poison * 5
            elif kind in {"strength", "dexterity", "ritual_block", "retain_block", "next_attack"}:
                score += value * 8

        cost = int(card.get("cost", 0))
        score -= cost
        if cost == 0:
            score += 3
        return score

    @staticmethod
    def _estimate_incoming_damage(move: dict[str, Any] | None) -> int:
        if not move:
            return 0
        total = 0
        for effect in move.get("effects", []):
            if effect.get("kind") in {"damage", "lifesteal_damage"}:
                total += int(effect.get("value", 0)) * int(effect.get("times", 1))
        return total


async def choose_action_with_agent(
    adapter: RogueGameAdapter,
    agent_name: str = "heuristic",
) -> tuple[str, dict[str, Any], str, dict[str, Any]]:
    state = adapter.get_state()
    legal_actions = adapter.get_legal_actions()
    heuristic = HeuristicRogueAgent()
    if agent_name == "llm":
        try:
            return await LLMRogueAgent().choose_action(state, legal_actions)
        except Exception as exc:
            action, params, reason = heuristic.choose_action(state, legal_actions)
            return action, params, f"LLM 决策失败，启发式兜底：{exc}; {reason}", {"fallback_error": str(exc)}
    action, params, reason = heuristic.choose_action(state, legal_actions)
    return action, params, reason, {"decision": {"action": action, "params": params, "reason": reason}}


async def step_auto(
    adapter: RogueGameAdapter,
    agent_name: str = "heuristic",
) -> dict[str, Any]:
    state = adapter.get_state()
    phase = state.get("phase")
    if phase in {"game_over", "victory"}:
        return {"status": "done", "reason": phase, "state": state}
    if phase != "combat":
        action = "start_combat"
        params: dict[str, Any] = {"enemy_type": "normal"}
        reason = "非战斗阶段，执行默认推进"
        if phase == "map":
            action, params, reason = "choose_node", {"index": 0}, "选择第一条可用路线"
        elif phase == "reward":
            rewards = state.get("pending_reward", [])
            if rewards:
                action, params, reason = "pick_reward", {"index": 0}, "选择第一张战斗奖励"
            else:
                action, params, reason = "skip_reward", {}, "没有奖励牌，跳过奖励"
        elif phase == "shop":
            action, params, reason = "shop_leave", {}, "自动策略暂不购物，离开商店"
        elif phase == "choice":
            action, params, reason = "choice_select", {"index": 0}, "选择第一个事件选项"
        response = adapter.execute_action(action, params)
        return {
            "status": "success",
            "agent": agent_name,
            "action": action,
            "params": params,
            "reason": reason,
            "response": response,
            "state": adapter.get_state(),
            "legal_actions": adapter.get_legal_actions(),
        }
    action, params, reason, llm_info = await choose_action_with_agent(adapter, agent_name)
    response = adapter.execute_action(action, params)
    return {
        "status": "success",
        "agent": agent_name,
        "action": action,
        "params": params,
        "reason": reason,
        "llm": llm_info,
        "response": response,
        "state": adapter.get_state(),
        "legal_actions": adapter.get_legal_actions(),
    }


def run_auto(
    role_id: str = "exile",
    seed: int | None = None,
    combats: int = 1,
    max_actions: int = 200,
    verbose: bool = True,
    agent_name: str = "heuristic",
) -> AutoRunResult:
    adapter = RogueGameAdapter(role_id=role_id, seed=seed)
    result = AutoRunResult(role_id=role_id, seed=seed, combats_requested=combats)

    while result.combats_finished < combats and result.actions < max_actions:
        if adapter.get_state().get("phase") == "game_over":
            result.losses += 1
            break
        step = asyncio.run(step_auto(adapter, agent_name))
        response = step.get("response", {})
        result.actions += 1
        line = (
            f"[{result.actions:03d}] {step.get('action')} {step.get('params')} | "
            f"{step.get('reason')} | {_format_response(response)}"
        )
        result.log.append(line)
        if verbose:
            print(line)

        payload = response.get("result", {})
        if payload.get("combat_result") in {"won", "lost"}:
            result.combats_finished += 1
            if payload["combat_result"] == "won":
                result.wins += 1
            else:
                result.losses += 1
                break

    result.final_state = adapter.get_state()
    if verbose:
        print(
            f"\n自动游玩结束：战斗 {result.combats_finished}/{combats}，"
            f"胜 {result.wins}，负 {result.losses}，动作数 {result.actions}"
        )
    return result


def _format_response(response: dict[str, Any]) -> str:
    if response.get("status") == "error":
        err = response.get("error", {})
        return f"ERROR {err.get('code')}: {err.get('message')}"
    action = response.get("action", "unknown")
    payload = response.get("result", {})
    if payload.get("combat_result"):
        return f"{action}: combat_result={payload['combat_result']}"
    state = payload.get("state", {})
    combat = state.get("combat", {})
    player = state.get("player", {})
    enemy = combat.get("enemy", {})
    if combat:
        return (
            f"{action}: HP {player.get('hp')}/{player.get('max_hp')} "
            f"E {player.get('energy')}/{player.get('energy_max')} | "
            f"{enemy.get('name')} {enemy.get('hp')}/{enemy.get('max_hp')}"
        )
    return f"{action}: ok"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="数值之塔自动玩家")
    parser.add_argument("--role", choices=["exile", "toxicist", "burner"], default="exile")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--combats", type=int, default=1)
    parser.add_argument("--max-actions", type=int, default=200)
    parser.add_argument("--agent", choices=["heuristic", "llm"], default="heuristic")
    parser.add_argument("--quiet", action="store_true")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    run_auto(
        role_id=args.role,
        seed=args.seed,
        combats=args.combats,
        max_actions=args.max_actions,
        verbose=not args.quiet,
        agent_name=args.agent,
    )


if __name__ == "__main__":
    main()
