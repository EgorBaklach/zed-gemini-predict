"""HTTP layer: OpenAI-compatible `/v1/completions` endpoint for Zed (`open_ai_compatible_api`)."""
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config
from .fim import build_fim_prompt, parse_fim_prompt
from .gemini import GeminiClient, GeminiError, GeminiReply
from .php import PROFILE
from .pipeline import postprocess

GEMINI = GeminiClient()
PLACEHOLDER_KEYS = ("dummy", "local")


def log(message: str) -> None:
    print(f"[zed-fim-proxy] {message}", flush=True)


def resolve_model(requested: str) -> str:
    """Zed may send any model name; only Gemini 3.x names are passed through."""
    return requested if requested.startswith("gemini-3.") else config.DEFAULT_GEMINI_MODEL


def completion_response(model: str, text: str, prompt_tokens: int = 0, completion_tokens: int = 0, total_tokens: int = 0) -> dict:
    now = time.time()
    return {
        "id": f"cmpl-{int(now * 1000)}",
        "object": "text_completion",
        "created": int(now),
        "model": model,
        "choices": [{"text": text, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": total_tokens},
    }


def write_debug_log(prefix: str, suffix: str, decision: str, text: str = "", rules: list[str] | None = None,
                    reply: GeminiReply | None = None) -> None:
    """
    One JSON line per request. `decision`: `local` (deterministic answer), `skip` (gatekeeper, silent)
    or `llm` (Gemini answer + which rules changed it).
    """
    entry = {
        "ts": int(time.time()),
        "decision": decision,
        "prefix_tail": prefix[-160:],
        "suffix_head": suffix[:160],
        "cleaned_text": text,
        "rules": rules or [],
    }
    if reply is not None:
        entry.update({
            "latency_ms": reply.latency_ms,
            "tokens": f"{reply.prompt_tokens}+{reply.completion_tokens}",
            "finish_reason": reply.finish_reason,
            "raw_text": reply.text,
        })
    try:
        with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


class FimProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log(f"{self.address_string()} - {fmt % args}")

    def do_POST(self):
        if not self.path.startswith("/v1/completions"):
            self.send_error(404, "Not Found")
            return

        payload = self._read_json()
        if payload is None:
            return
        api_key = self._api_key()
        if not api_key:
            self._send_json(401, {"error": "Missing Gemini API key in Authorization header or GEMINI_API_KEY env"})
            return

        req_model = payload.get("model", config.DEFAULT_GEMINI_MODEL)
        max_tokens = int(payload.get("max_tokens") or config.DEFAULT_MAX_TOKENS)
        prefix, suffix = parse_fim_prompt(payload.get("prompt", ""))

        # Deterministic local completion (e.g. closing a block the developer opened): 0 tokens, ~1 ms
        local = PROFILE.local_completion(prefix, suffix)
        if local:
            name = f"local:{PROFILE.local_completion.__name__}"
            write_debug_log(prefix, suffix, "local", local, [name])
            log(f"LOCAL {name} -> {local!r}")
            self._send_json(200, completion_response(req_model, local))
            return

        # Pre-flight Open Semantic Slot guard (0 ms, 0 tokens, zero architectural invention)
        if PROFILE.should_skip(prefix, suffix):
            write_debug_log(prefix, suffix, "skip")
            self._send_json(200, completion_response(req_model, ""))
            return

        gemini_model = resolve_model(req_model)
        try:
            reply = GEMINI.generate(gemini_model, api_key, PROFILE.system_instruction, build_fim_prompt(prefix, suffix), max_tokens)
        except GeminiError as e:
            log(f"Gemini HTTP {e.status}: {e.body[:300]}")
            self._send_json(e.status, {"error": e.body})
            return
        except Exception as e:
            log(f"Request error: {e}")
            self._send_json(502, {"error": str(e)})
            return

        text, rules = postprocess(reply.text, prefix, suffix, PROFILE)
        write_debug_log(prefix, suffix, "llm", text, rules, reply)
        log(
            f"OK model={gemini_model} latency={reply.latency_ms}ms "
            f"tokens={reply.prompt_tokens}+{reply.completion_tokens} finish={reply.finish_reason} "
            f"raw={reply.text[:40]!r} -> clean={text[:40]!r} rules={','.join(rules) or '-'}"
        )
        self._send_json(200, completion_response(
            req_model, text, reply.prompt_tokens, reply.completion_tokens, reply.total_tokens,
        ))

    def _read_json(self) -> dict | None:
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception as e:
            self._send_json(400, {"error": f"Invalid JSON: {e}"})
            return None

    def _api_key(self) -> str:
        """Bearer token from Zed, unless it is a placeholder - then the key from the environment."""
        auth = self.headers.get("Authorization", "")
        key = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        return config.ENV_API_KEY if not key or key in PLACEHOLDER_KEYS else key

    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = ThreadingHTTPServer((config.HOST, config.PORT), FimProxyHandler)
    log(
        f"Listening on http://{config.HOST}:{config.PORT}/v1/completions "
        f"(default model: {config.DEFAULT_GEMINI_MODEL}, language: {PROFILE.name}, rules: {len(PROFILE.rules)})"
    )
    server.serve_forever()
