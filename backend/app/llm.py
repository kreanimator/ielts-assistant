"""Streams chat replies from any OpenAI-compatible server."""
import json
import re
from collections.abc import AsyncIterator

import httpx

from . import config

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


async def stream_reply(messages: list[dict]) -> AsyncIterator[str]:
    """Yields the reply text piece by piece as the model writes it."""
    payload = {
        "model": config.LLM_MODEL,
        "messages": messages,
        "stream": True,
        "temperature": 0.7,
        # A spoken reply must start fast, so no hidden "thinking" step.
        "chat_template_kwargs": {"enable_thinking": False},
    }
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("POST", f"{config.LLM_URL}/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line.removeprefix("data: ")
                if data == "[DONE]":
                    break
                text = json.loads(data)["choices"][0]["delta"].get("content")
                if text:
                    yield text


async def stream_sentences(messages: list[dict]) -> AsyncIterator[str]:
    """Yields whole sentences, so speech can start before the reply is finished."""
    buffer = ""
    async for text in stream_reply(messages):
        buffer += text
        *sentences, buffer = SENTENCE_END.split(buffer)
        for sentence in sentences:
            yield sentence.strip()
    if buffer.strip():
        yield buffer.strip()
