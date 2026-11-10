"""Streams chat replies from any OpenAI-compatible server."""
import asyncio
import json
import re
from collections.abc import AsyncIterator

import httpx

from . import config

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


async def model_name() -> str:
    """The model the LLM server is running, or the configured name if it can't be reached."""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(f"{config.LLM_URL}/models")
            return response.json()["data"][0]["id"]
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        return config.LLM_MODEL


async def complete_json(messages: list[dict], schema: dict) -> dict:
    """A reply that is guaranteed to match the JSON schema (llama.cpp enforces it while generating)."""
    payload = {
        "model": config.LLM_MODEL,
        "messages": messages,
        "temperature": 0.2,
        "chat_template_kwargs": {"enable_thinking": False},
        "response_format": {"type": "json_schema", "json_schema": {"name": "reply", "schema": schema}},
    }
    async with httpx.AsyncClient(timeout=300) as client:  # long: the server may be busy with a chat
        for attempt in range(2):  # once more if the server was full (its context is shared by all requests)
            response = await client.post(f"{config.LLM_URL}/chat/completions", json=payload)
            if response.status_code < 500 or attempt:
                break
            await asyncio.sleep(2)
        response.raise_for_status()
        return json.loads(response.json()["choices"][0]["message"]["content"])


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
