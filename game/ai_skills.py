from __future__ import annotations

from typing import Any


AI_SKILLS: list[dict[str, Any]] = [
    {
        "name": "choose_role",
        "description": "选择本局角色。只能在非战斗阶段调用。",
        "input_schema": {
            "role_id": "string, one of: exile, toxicist, burner"
        },
        "output_description": {
            "player": "object, 初始化后的玩家状态"
        },
    },
    {
        "name": "start_combat",
        "description": "开始一场战斗并进入玩家第 1 回合。",
        "input_schema": {
            "enemy_type": "string, one of: normal, elite, boss",
            "act": "optional integer, 当前章节，默认沿用适配器 act"
        },
        "output_description": {
            "state": "object, 新战斗状态，包含玩家、敌人、手牌、合法动作"
        },
    },
    {
        "name": "play_card",
        "description": "使用当前手牌中的一张技能牌。优先使用 hand_index，因为同 id 卡牌可能重复。",
        "input_schema": {
            "hand_index": "integer, 当前 hand 数组里的 0-based 索引",
            "card_id": "optional string, 当没有 hand_index 时可用卡牌 id"
        },
        "output_description": {
            "played": "object, 被使用的卡牌",
            "logs": "array of string, 本动作新增日志",
            "state": "object, 动作后的游戏状态"
        },
    },
    {
        "name": "end_turn",
        "description": "结束玩家回合，执行敌人回合，并在双方存活时进入下一玩家回合。",
        "input_schema": {},
        "output_description": {
            "logs": "array of string, 回合结算日志",
            "state": "object, 新回合或战斗结束后的状态"
        },
    },
]


def get_ai_skill_list() -> list[dict[str, Any]]:
    return AI_SKILLS
