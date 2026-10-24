"""Thin LLM wrapper: Bedrock Converse or a local Ollama, picked by settings.LLM_PROVIDER.

The Bedrock client is created lazily; tests inject a Converse-shaped stub with set_client(), which
takes priority over either provider.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.request

from lantern_core.config import settings

log = logging.getLogger(__name__)

_client = None


def set_client(client) -> None:
    global _client
    _client = client


def get_client():
    global _client
    if _client is None:
        from botocore.config import Config

        from lantern_core.store import _aws_session

        cfg = Config(
            read_timeout=settings.BEDROCK_TIMEOUT_S,
            connect_timeout=min(3.0, settings.BEDROCK_TIMEOUT_S),
            retries={"max_attempts": 1, "mode": "standard"},
        )
        _client = _aws_session().client("bedrock-runtime", region_name=settings.AWS_REGION, config=cfg)
    return _client


def model_ids() -> list[str]:
    return settings.llm_model_ids


def provider() -> str:
    return settings.LLM_PROVIDER


def _ollama_chat(model_id: str, system: str, user: str, max_tokens: int, temperature: float) -> str:
    body = {
        "model": model_id,
        "stream": False,
        "format": "json",  # both callers want a JSON object back
        "keep_alive": settings.OLLAMA_KEEP_ALIVE,
        "options": {"temperature": temperature, "num_predict": max_tokens},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        settings.OLLAMA_BASE_URL.rstrip("/") + "/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=settings.OLLAMA_TIMEOUT_S) as resp:
        return json.load(resp)["message"]["content"]


def converse_text(model_id: str, system: str, user: str, max_tokens: int = 600, temperature: float = 0.2) -> str:
    t0 = time.perf_counter()
    if _client is None and settings.LLM_PROVIDER == "ollama":
        text = _ollama_chat(model_id, system, user, max_tokens, temperature)
        log.info("ollama chat model=%s latency_ms=%.0f", model_id, (time.perf_counter() - t0) * 1000)
        return text
    resp = get_client().converse(
        modelId=model_id,
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
    )
    parts = resp["output"]["message"]["content"]
    text = "".join(p.get("text", "") for p in parts)
    log.info("bedrock converse model=%s latency_ms=%.0f", model_id, (time.perf_counter() - t0) * 1000)
    return text


def extract_json(text: str) -> dict:
    """Parse the first JSON object in a model reply (tolerates code fences and chatter)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in model reply")
    obj = json.loads(text[start : end + 1])
    if not isinstance(obj, dict):
        raise ValueError("model reply is not a JSON object")
    return obj


def warm() -> tuple[str, float]:
    """Load the primary model so the first judged click is fast (Ollama cold load is ~20 s)."""
    model = model_ids()[0]
    t0 = time.perf_counter()
    converse_text(model, 'Reply with JSON only: {"ok": true}', "ping", max_tokens=10, temperature=0.0)
    return model, time.perf_counter() - t0
