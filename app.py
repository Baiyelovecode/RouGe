from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from game.ai_adapter import RogueGameAdapter
from game.auto_player import step_auto


BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="数值之塔 Web UI", version="0.2.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

_adapter = RogueGameAdapter(role_id="exile")
_history: list[dict[str, Any]] = []


class NewGameRequest(BaseModel):
    role_id: str = "exile"
    seed: int | None = None


class StepRequest(BaseModel):
    agent: str = "llm"


class ActionRequest(BaseModel):
    action: str
    params: dict[str, Any] = Field(default_factory=dict)


@app.get("/", response_class=HTMLResponse)
async def index():
    with open(BASE_DIR / "static" / "index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.post("/api/new")
async def new_game(request: NewGameRequest):
    global _adapter, _history
    _adapter = RogueGameAdapter(role_id=request.role_id, seed=request.seed)
    _history = []
    return _snapshot()


@app.get("/api/state")
async def get_state():
    return _snapshot()


@app.post("/api/step")
async def step(request: StepRequest):
    step_result = await step_auto(_adapter, request.agent)
    _history.append(step_result)
    return _snapshot(extra={"last_step": step_result})


@app.post("/api/action")
async def action(request: ActionRequest):
    result = _adapter.execute_action(request.action, request.params)
    _history.append({
        "status": result.get("status"),
        "agent": "player",
        "action": request.action,
        "params": request.params,
        "reason": "玩家手动操作",
        "response": result,
    })
    return _snapshot(extra={"last_action": result})


def _snapshot(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    data = {
        "state": _adapter.get_state(),
        "legal_actions": _adapter.get_legal_actions(),
        "history": _history[-50:],
    }
    if extra:
        data.update(extra)
    return data


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8010, reload=True)
