"""POST /chat: cash-flow Q&A. Off (503) unless the FREERISE_LLM_* env vars are set."""

import logging
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from freerise import chat
from freerise.api.deps import DB, today

router = APIRouter()
log = logging.getLogger("freerise.chat")


class ChatStatus(BaseModel):
    enabled: bool


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ChatIn(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=20)


class ChatOut(BaseModel):
    reply: str


@router.get("/chat/status")
def chat_status() -> ChatStatus:
    return ChatStatus(enabled=chat.llm_config() is not None)


@router.post("/chat")
def ask(body: ChatIn, db: DB) -> ChatOut:
    cfg = chat.llm_config()
    if cfg is None:
        raise HTTPException(503, "chat is not configured")
    try:
        reply = chat.answer(db, today(), [m.model_dump() for m in body.messages], cfg)
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        # Type only: the request and response carry the household's numbers.
        log.error("chat failed: %s", type(e).__name__)
        raise HTTPException(502, "the language model did not answer") from None
    return ChatOut(reply=reply)
