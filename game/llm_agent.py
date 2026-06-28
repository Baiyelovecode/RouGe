from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any

import httpx


SYSTEM_PROMPT = """你是一个肉鸽爬塔游戏 AI 玩家。
你只能从输入 legal_actions 里选择一个合法动作，不得编造手牌、敌人、能量或参数。
目标是在当前战斗中提高胜率：优先斩杀，其次防止受到致命伤害，再考虑长期增益。
只输出 JSON，不要输出 Markdown。
输出格式：
{
  "action": "play_card | end_turn | start_combat",
  "params": {},
  "reason": "简短中文理由"
}
"""


def _load_default_config() -> dict[str, Any]:
    """优先读环境变量；没有时复用 uav-brain-demo/config.py 里的本地配置。"""
    config = {
        "api_key": os.environ.get("DEEPSEEK_API_KEY", ""),
        "api_base": os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com"),
        "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        "timeout": int(os.environ.get("LLM_TIMEOUT_SEC", "30")),
    }
    if config["api_key"]:
        return config

    sibling_config = Path(__file__).resolve().parents[2] / "uav-brain-demo" / "config.py"
    if sibling_config.exists():
        spec = importlib.util.spec_from_file_location("uav_brain_config", sibling_config)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            config["api_key"] = getattr(module, "DEEPSEEK_API_KEY", "")
            config["api_base"] = getattr(module, "DEEPSEEK_API_BASE", config["api_base"])
            config["model"] = getattr(module, "DEEPSEEK_MODEL", config["model"])
            config["timeout"] = getattr(module, "LLM_TIMEOUT_SEC", config["timeout"])
    return config


class LLMRogueAgent:
    """基于 OpenAI-compatible Chat Completions 的肉鸽动作选择器。"""

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ) -> None:
        defaults = _load_default_config()
        self.api_key = api_key or defaults["api_key"]
        self.api_base = (api_base or defaults["api_base"]).rstrip("/")
        self.model = model or defaults["model"]
        self.timeout = timeout or defaults["timeout"]

    async def choose_action(
        self,
        state: dict[str, Any],
        legal_actions: list[dict[str, Any]],
    ) -> tuple[str, dict[str, Any], str, dict[str, Any]]:
        if not self.api_key:
            raise RuntimeError("未配置 DEEPSEEK_API_KEY")

        legal = [item for item in legal_actions if item.get("legal", True)]
        prompt = {
            "state": self._compact_state(state),
            "legal_actions": legal,
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False, indent=2)},
            ],
            "temperature": 0.1,
            "max_tokens": 800,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.api_base}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        decision = self._extract_json(content)
        action = str(decision.get("action", ""))
        params = decision.get("params", {})
        if not isinstance(params, dict):
            params = {}
        reason = str(decision.get("reason", "LLM 未给出理由"))
        self._validate_decision(action, params, legal)
        return action, params, reason, {"raw": content, "decision": decision}

    def _validate_decision(
        self,
        action: str,
        params: dict[str, Any],
        legal_actions: list[dict[str, Any]],
    ) -> None:
        for item in legal_actions:
            if item.get("action") != action:
                continue
            expected = item.get("params", {})
            if all(params.get(k) == v for k, v in expected.items()):
                return
            if action in {"end_turn", "start_combat"}:
                return
        raise ValueError(f"LLM 选择了非法动作: {action} {params}")

    @staticmethod
    def _compact_state(state: dict[str, Any]) -> dict[str, Any]:
        player = state.get("player", {})
        combat = state.get("combat", {})
        enemy = combat.get("enemy", {})
        return {
            "phase": state.get("phase"),
            "act": state.get("act"),
            "floor": state.get("floor"),
            "player": {
                "name": player.get("name"),
                "hp": player.get("hp"),
                "max_hp": player.get("max_hp"),
                "block": player.get("block"),
                "energy": player.get("energy"),
                "energy_max": player.get("energy_max"),
                "strength": player.get("strength"),
                "dexterity": player.get("dexterity"),
                "statuses": player.get("statuses", {}),
                "relics": player.get("relics", []),
            },
            "enemy": enemy,
            "hand": combat.get("hand", []),
            "log": combat.get("log", []),
        }

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            first_newline = text.find("\n")
            if first_newline >= 0:
                text = text[first_newline + 1:]
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3].rstrip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start:end + 1])
            raise
