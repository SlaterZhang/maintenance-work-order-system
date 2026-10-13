"""AI 助手服务：配置文件读写 + LLM 流式转发 + 模型管理。

为什么走后端代理而不是浏览器直连：
- ecloud 端点不带 CORS 头（预检 401），浏览器直连会被拦；
- API key 放服务端配置文件，不落前端，泄露面最小。

配置文件：src/ai_config.json（可直接编辑，改完重启 ims-d；或由页面「设置」
由系统管理员增删模型——写回同一文件）。系统管理员=角色含 ADMIN_ALL。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.application import auth_service
from src.infrastructure.db import get_db
from src.interfaces.http.deps import trace_id

router = APIRouter(prefix="/api/v1/ai", tags=["AI 助手"])

CONFIG_PATH = Path(__file__).resolve().parents[2] / "ai_config.json"


# ─────────────────────────── 配置读写 ───────────────────────────

def load_config() -> dict[str, Any]:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"providers": [], "thinkingLevels": {}, "defaultThinking": "normal"}


def save_config(cfg: dict[str, Any]) -> None:
    CONFIG_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def _require_admin(db: Session, authorization: str | None) -> None:
    """仅系统管理员（角色含 ADMIN_ALL / 权限含 ADMIN_ALL）可增删模型。"""
    ctx = auth_service.current_user_context(db, authorization)
    role_codes = set(ctx.get("roleCodes") or [])
    perms = set(ctx.get("permissions") or [])
    if not (role_codes & {"ADMIN_ALL", "SYSTEM_ADMIN"} or "ADMIN_ALL" in perms):
        raise HTTPException(status_code=403, detail="仅系统管理员可管理 AI 模型")


def _provider(cfg: dict[str, Any], provider_id: str | None) -> dict[str, Any]:
    providers = cfg.get("providers") or []
    if not providers:
        raise HTTPException(status_code=503, detail="AI 未配置：请在 src/ai_config.json 里填写 providers")
    if provider_id:
        for p in providers:
            if p.get("id") == provider_id:
                return p
        raise HTTPException(status_code=404, detail=f"未找到 AI 服务商 {provider_id}")
    default = cfg.get("defaultProvider") or providers[0].get("id")
    for p in providers:
        if p.get("id") == default:
            return p
    return providers[0]


# ─────────────────────────── 模型管理 ───────────────────────────

class ModelIn(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    thinking: bool = False
    provider_id: str | None = Field(default=None, max_length=80)


@router.get("/config")
def get_ai_config(
    x_trace_id: str = Depends(trace_id),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """模型清单（key 打码）+ 思考强度档位 + 默认项 —— 登录即可读，供页面渲染。"""
    auth_service.current_user_context(db, authorization)
    cfg = load_config()
    providers = []
    for p in cfg.get("providers") or []:
        providers.append({
            "id": p.get("id"), "name": p.get("name"),
            "defaultModel": p.get("defaultModel"),
            "models": [
                {"id": m.get("id"), "name": m.get("name"), "thinking": bool(m.get("thinking"))}
                for m in p.get("models") or []
            ],
        })
    return {
        "providers": providers,
        "thinkingLevels": cfg.get("thinkingLevels") or {},
        "defaultThinking": cfg.get("defaultThinking") or "normal",
        "isAdmin": _is_admin(db, authorization),
    }


def _is_admin(db: Session, authorization: str | None) -> bool:
    try:
        _require_admin(db, authorization)
        return True
    except HTTPException:
        return False


@router.post("/models")
def add_model(
    body: ModelIn,
    x_trace_id: str = Depends(trace_id),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """系统管理员新增模型（写回 ai_config.json）。"""
    _require_admin(db, authorization)
    cfg = load_config()
    provider = _provider(cfg, body.provider_id)
    if any(m.get("id") == body.model_id for m in provider.get("models") or []):
        raise HTTPException(status_code=409, detail=f"模型 {body.model_id} 已存在")
    provider.setdefault("models", []).append(
        {"id": body.model_id, "name": body.name, "thinking": body.thinking})
    if not provider.get("defaultModel"):
        provider["defaultModel"] = body.model_id
    save_config(cfg)
    return {"ok": True, "models": provider["models"]}


@router.delete("/models/{model_id}")
def delete_model(
    model_id: str,
    x_trace_id: str = Depends(trace_id),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """系统管理员删除模型（写回 ai_config.json）。"""
    _require_admin(db, authorization)
    cfg = load_config()
    provider = _provider(cfg, None)
    models = provider.get("models") or []
    remain = [m for m in models if m.get("id") != model_id]
    if len(remain) == len(models):
        raise HTTPException(status_code=404, detail=f"模型 {model_id} 不存在")
    if not remain:
        raise HTTPException(status_code=409, detail="至少保留一个模型")
    provider["models"] = remain
    if provider.get("defaultModel") == model_id:
        provider["defaultModel"] = remain[0]["id"]
    save_config(cfg)
    return {"ok": True, "models": remain}


# ─────────────────────────── 流式对话 ───────────────────────────

class ChatIn(BaseModel):
    messages: list[dict[str, str]] = Field(min_length=1)
    model: str | None = Field(default=None, max_length=120)
    provider_id: str | None = Field(default=None, max_length=80)
    thinking: str | None = Field(default=None, max_length=20,
                                 description="brief | normal | deep（映射 max_tokens 上限）")


async def _forward_stream(provider: dict[str, Any], payload: dict[str, Any]) -> AsyncIterator[bytes]:
    url = provider["baseUrl"].rstrip("/") + "/chat/completions"
    headers = {"Authorization": "Bearer " + provider["apiKey"],
               "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            if resp.status_code >= 400:
                text = (await resp.aread()).decode("utf-8", "replace")[:500]
                yield f'data: {json.dumps({"error": f"上游 {resp.status_code}: {text}"}, ensure_ascii=False)}\n\n'.encode()
                return
            async for chunk in resp.aiter_bytes():
                yield chunk


@router.post("/chat")
async def chat(
    body: ChatIn,
    x_trace_id: str = Depends(trace_id),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """流式对话（SSE 原样透传）。登录即可用；知识库上下文由前端组装进 messages。"""
    auth_service.current_user_context(db, authorization)
    cfg = load_config()
    provider = _provider(cfg, body.provider_id)
    levels = cfg.get("thinkingLevels") or {}
    level = levels.get(body.thinking or cfg.get("defaultThinking") or "normal") or {}
    payload: dict[str, Any] = {
        "model": body.model or provider.get("defaultModel") or "deepseek-v4.1-flash",
        "messages": body.messages,
        "stream": True,
        "max_tokens": level.get("maxTokens", 1024),
    }
    return StreamingResponse(_forward_stream(provider, payload),
                             media_type="text/event-stream")
