import io
import json

from explain import bedrock_client
from lantern_core.config import settings


def test_model_ids_follow_provider(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "bedrock")
    assert bedrock_client.model_ids() == [settings.BEDROCK_MODEL_ID, settings.BEDROCK_FALLBACK_MODEL_ID]
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    assert bedrock_client.model_ids() == [settings.OLLAMA_MODEL, settings.OLLAMA_FALLBACK_MODEL]


def test_ollama_chat_request_shape(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    seen = {}

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["body"] = json.loads(req.data)
        seen["timeout"] = timeout
        return io.BytesIO(json.dumps({"message": {"content": '{"ok": true}'}}).encode())

    monkeypatch.setattr(bedrock_client.urllib.request, "urlopen", fake_urlopen)
    out = bedrock_client.converse_text("qwen2.5:7b", "sys", "hi", max_tokens=50, temperature=0.0)
    assert bedrock_client.extract_json(out) == {"ok": True}
    assert seen["url"] == settings.OLLAMA_BASE_URL.rstrip("/") + "/api/chat"
    assert seen["body"]["model"] == "qwen2.5:7b" and seen["body"]["format"] == "json"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "sys"}
    assert seen["timeout"] == settings.OLLAMA_TIMEOUT_S


def test_injected_stub_wins_over_ollama(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")

    class Stub:
        def converse(self, **_kw):
            return {"output": {"message": {"content": [{"text": "stub"}]}}}

    bedrock_client.set_client(Stub())
    assert bedrock_client.converse_text("any", "s", "u") == "stub"
