"""Gemini generateContent client over a single persistent (keep-alive) TLS connection."""
import http.client
import json
import threading
import time
from dataclasses import dataclass

from .fim import STOP_SEQUENCES

GEMINI_HOST = "generativelanguage.googleapis.com"


class GeminiError(Exception):
    """Gemini answered with a non-200 HTTP status."""

    def __init__(self, status: int, body: str):
        super().__init__(f"Gemini HTTP {status}")
        self.status = status
        self.body = body


@dataclass
class GeminiReply:
    text: str
    finish_reason: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: int


class GeminiClient:
    def __init__(self, timeout: int = 15):
        self._timeout = timeout
        self._lock = threading.Lock()
        self._conn: http.client.HTTPSConnection | None = None

    def generate(self, model: str, api_key: str, system_instruction: str, user_prompt: str, max_tokens: int) -> GeminiReply:
        body = {
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": max_tokens,
                "stopSequences": STOP_SEQUENCES,
                "thinkingConfig": {"thinkingLevel": "MINIMAL"},
            },
        }
        path = f"/v1beta/models/{model}:generateContent?key={api_key}"

        t0 = time.monotonic()
        status, data = self._post(path, json.dumps(body).encode("utf-8"))
        latency_ms = int((time.monotonic() - t0) * 1000)

        if status != 200:
            raise GeminiError(status, data.decode("utf-8", errors="replace"))
        return self._parse(json.loads(data.decode("utf-8")), latency_ms)

    @staticmethod
    def _parse(resp: dict, latency_ms: int) -> GeminiReply:
        text, finish_reason = "", "UNKNOWN"
        candidates = resp.get("candidates") or []
        if candidates:
            finish_reason = candidates[0].get("finishReason", "UNKNOWN")
            parts = (candidates[0].get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))

        usage = resp.get("usageMetadata") or {}
        prompt_tokens = int(usage.get("promptTokenCount") or 0)
        completion_tokens = int(usage.get("candidatesTokenCount") or 0)
        total_tokens = int(usage.get("totalTokenCount") or (prompt_tokens + completion_tokens))
        return GeminiReply(text, finish_reason, prompt_tokens, completion_tokens, total_tokens, latency_ms)

    def _post(self, path: str, body: bytes) -> tuple[int, bytes]:
        """POST over the shared connection; one transparent reconnect if the kept-alive socket went stale."""
        with self._lock:
            for attempt in range(2):
                try:
                    if self._conn is None:
                        self._conn = http.client.HTTPSConnection(GEMINI_HOST, timeout=self._timeout)
                    self._conn.request(
                        "POST", path, body=body,
                        headers={"Content-Type": "application/json", "Connection": "keep-alive"},
                    )
                    resp = self._conn.getresponse()
                    return resp.status, resp.read()
                except Exception:
                    try:
                        if self._conn is not None:
                            self._conn.close()
                    except Exception:
                        pass
                    self._conn = None
                    if attempt == 1:
                        raise
        return 502, b"{}"
