#!/usr/bin/env python3
"""
Lightweight FIM-to-Gemini proxy for Zed Edit Predictions (open_ai_compatible_api).
Listens on http://127.0.0.1:8089/v1/completions
Uses persistent HTTPS Keep-Alive + Gemini 3.5 Flash Lite (thinkingLevel=MINIMAL)
with the Universal Syntactic Determinism Law.
"""
import http.client
import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = os.environ.get("ZED_PROXY_HOST", "127.0.0.1")
PORT = int(os.environ.get("ZED_PROXY_PORT", "8089"))
DEFAULT_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
ENV_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
DEBUG_LOG_PATH = os.environ.get("ZED_PROXY_DEBUG_LOG", "/tmp/zed_fim_debug.log")

SYSTEM_INSTRUCTION = (
    "Role: Local Syntax & Idiom Code Completer for Modern PHP 8.2/8.3+ (strict_types, typed properties/returns, readonly, backed enums, traits, match, arrow functions, constructor promotion, nullsafe ?->).\n"
    "Insert ONLY the exact raw PHP code at <|fim_middle|> that seamlessly bridges <|fim_prefix|> and <|fim_suffix|>.\n"
    "Scope:\n"
    "- Syntactic & statement closure: finish started conditions, loops (foreach/for), function/method calls, fluent method chains, strings, brackets, and ALWAYS include the trailing semicolon (;) when completing a PHP statement at the end of a line.\n"
    "- Structural skeleton closure: if <|fim_prefix|> ends with an unclosed block like `try {` (and `catch` is missing in <|fim_suffix|>), complete the minimal valid skeleton (e.g. `\\n} catch (\\Throwable $e) {\\n}`).\n"
    "- Idiomatic refactoring: transform local expressions between forms using ONLY existing local variables. In PHP, `function (...) use (...)` MUST use `{ return ...; }` (never `=>`), and `fn(...)` MUST use `=>`.\n"
    "- Mechanical continuation: complete repetitive array keys/items, enum cases (`case Name = 'value';`), constructor properties, or interface/trait signatures matching the immediate pattern.\n"
    "Strict Constraints:\n"
    "1. ZERO architecture/domain invention: never invent new `&&`/`||` conditions, unrelated methods, classes, design patterns, DB/API logic, or subsequent business statements.\n"
    "2. Count parentheses/brackets carefully: close ONLY the parentheses/brackets that are actually open in the current line of <|fim_prefix|>.\n"
    "3. Respect <|fim_suffix|>: NEVER output closing tokens or lines that ALREADY exist at the beginning of <|fim_suffix|>.\n"
    "4. Output raw PHP code ONLY: no markdown fences (```), no prose, no FIM tags."
)

_tls_lock = threading.Lock()
_tls_conn = None

# Open Semantic Slot detector: matches lines where no concrete expression/token has been started yet,
# so any completion would be pure semantic/architectural guessing.
_OPEN_SEMANTIC_SLOT_RE = re.compile(
    r"^("
    r"\s*|"  # 1. Blank / whitespace-only line
    r"\s*[\{\}\(\)\[\];,\'\"]+\s*|"  # 2. Only bare punctuation, braces, or a bare opening quote (' or ") on the line
    r"\s*\}?\s*(?:if|elseif|else|while|for|foreach|switch|match)\s*\(?\s*\)?\s*\{?\s*|"  # 3. Bare control keyword (including `} elseif (`) without condition
    r".*(?:=|\?\?=|\.=|return)\s*(?:match|switch|fn|function)\s*\(?\s*\)?\s*\{?\s*|"  # 4. Bare `$v = match (` / `return match (` without subject
    r"\s*(?:return|echo|print|throw|throw\s+new|yield|goto|new|clone)\s*|"  # 5. Bare statement/instantiation keyword without expression
    r"\s*(?:(?:public|protected|private|final|abstract|static|readonly)\s+)*(?:function|class|interface|trait|enum)\s*|"  # 6. Bare declaration keyword without identifier
    r"\s*\$[a-zA-Z0-9_]*\s*|"  # 7. Bare `$` or `$varName` on a line before any operator (`=`, `->`, etc.) is typed
    r"\s*\$[^\n=]+?(?<![=!<>])\s*(?:=|\.=|\?\?=|\+=|-=)\s*(?:new\s*)?[\[\(\'\"]?\s*|"  # 8. Any `$var = `, `$var = [`, `$var = '`, `$this->prop = ` with nothing inside yet
    r".*(?:->|\?->|::)\s*|"  # 9. Any line ending with bare `->`, `?->`, or `::` (waiting for LSP member completion)
    r"\s*(?://|#|\*).*|"  # 10. Inside a single-line or docblock comment line
    r"\s*[a-zA-Z_][a-zA-Z0-9_]*|"  # 11. Bare partial word/keyword (`fo`, `for`, `try` without `{` or trailing space) on a line
    r"\s*[а-яА-ЯёЁ]+\s*\(?\s*\)?\s*"  # 12. Accidental Cyrillic keyboard layout typo (e.g. `ш`, `ша()`)
    r")$"
)


def should_skip_request(prefix: str, suffix: str) -> bool:
    """
    Returns True if the cursor is at an Open Semantic Slot on the current line,
    or at the end of an already-closed statement/block header,
    avoiding any LLM call (0ms, 0 tokens, zero architectural hallucination).
    """
    current_line = prefix.rsplit("\n", 1)[-1]
    if _OPEN_SEMANTIC_SLOT_RE.match(current_line):
        return True
    current_stripped = current_line.strip()
    # Skip if the current line is already a completed statement ending with `;`
    if current_stripped.endswith(";"):
        return True
    # Skip if the current line is already a completed block header ending with `{` (except `try {` when catch is missing)
    if current_stripped.endswith("{") and not current_stripped.startswith("try"):
        return True
    # Skip if a closure on the current line was just closed with `}` before `);` in suffix and parens are already balanced
    suffix_same_line = suffix.split("\n", 1)[0].strip()
    if current_stripped.endswith("}") and suffix_same_line.endswith(";"):
        total_open = current_line.count("(") + suffix_same_line.count("(")
        total_close = current_line.count(")") + suffix_same_line.count(")")
        if total_open == total_close:
            return True
    # Skip if the cursor is right in the middle of an identifier/keyword token (e.g. `t|ry`, `f|or`, `$v|ar`)
    if prefix and suffix and (prefix[-1].isalnum() or prefix[-1] in ("_", "$")) and (suffix[0].isalnum() or suffix[0] == "_"):
        return True
    return False


def call_gemini_keepalive(path: str, body_bytes: bytes) -> tuple[int, bytes]:
    global _tls_conn
    with _tls_lock:
        for attempt in range(2):
            try:
                if _tls_conn is None:
                    _tls_conn = http.client.HTTPSConnection(
                        "generativelanguage.googleapis.com", timeout=15
                    )
                _tls_conn.request(
                    "POST",
                    path,
                    body=body_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "Connection": "keep-alive",
                    },
                )
                resp = _tls_conn.getresponse()
                data = resp.read()
                return resp.status, data
            except Exception:
                try:
                    if _tls_conn is not None:
                        _tls_conn.close()
                except Exception:
                    pass
                _tls_conn = None
                if attempt == 1:
                    raise
    return 502, b"{}"


def parse_fim_prompt(prompt: str) -> tuple[str, str]:
    if "<|fim_prefix|>" in prompt and "<|fim_suffix|>" in prompt:
        after_pre = prompt.split("<|fim_prefix|>", 1)[1]
        prefix, after_suf = after_pre.split("<|fim_suffix|>", 1)
        suffix = after_suf.split("<|fim_middle|>", 1)[0]
        return prefix, suffix
    if "<fim_prefix>" in prompt and "<fim_suffix>" in prompt:
        after_pre = prompt.split("<fim_prefix>", 1)[1]
        prefix, after_suf = after_pre.split("<fim_suffix>", 1)
        suffix = after_suf.split("<fim_middle>", 1)[0]
        return prefix, suffix
    if "[SUFFIX]" in prompt and "[PREFIX]" in prompt:
        after_suf = prompt.split("[SUFFIX]", 1)[1]
        suffix, prefix = after_suf.split("[PREFIX]", 1)
        return prefix, suffix
    return prompt, ""


def strip_suffix_overlap(text: str, suffix: str) -> str:
    if not text or not suffix:
        return text

    max_k = min(len(text), len(suffix))
    for k in range(max_k, 1, -1):
        if text.endswith(suffix[:k]):
            candidate = text[:-k]
            if candidate.strip():
                return candidate

    suffix_lstripped = suffix.lstrip(" \t\r\n")
    if suffix_lstripped:
        first_line = suffix_lstripped.splitlines()[0]
        max_k2 = min(len(text), len(first_line))
        for k in range(max_k2, 1, -1):
            overlap = first_line[:k]
            if overlap.strip() and text.endswith(overlap):
                candidate = text[:-k]
                if candidate.strip():
                    return candidate

    return text


def strip_prefix_repetition(text: str, prefix: str) -> str:
    if not text or not prefix:
        return text
    current_line = prefix.rsplit("\n", 1)[-1].strip()
    if len(current_line) >= 6:
        text_stripped = text.strip(" ()")
        if text_stripped == current_line or current_line.endswith(text_stripped):
            return ""
    return text


def fix_paren_and_semicolon_balance(text: str, prefix: str, suffix: str) -> str:
    if not text or "\n" in text:
        return text

    current_line_prefix = prefix.rsplit("\n", 1)[-1]
    suffix_same_line = suffix.split("\n", 1)[0].strip()

    # If closing a condition line (`if (...)`) and the model started with `)`
    # but then invented a brand-new ` && ...` or ` || ...` condition before `{`, strip the invented clause!
    current_line_stripped = current_line_prefix.lstrip()
    if (
        current_line_stripped.startswith(("if ", "if(", "elseif ", "elseif(", "} elseif", "while ", "while("))
        and text.startswith(")")
        and (" && " in text or " || " in text)
        and text.rstrip().endswith("{")
    ):
        text = ") {"

    open_parens = current_line_prefix.count("(") - current_line_prefix.count(")")
    suffix_net_close = max(0, suffix_same_line.count(")") - suffix_same_line.count("("))
    added_open = text.count("(")
    added_close = text.count(")")
    needed_close = max(0, open_parens + added_open - suffix_net_close)

    if suffix_same_line:
        while added_close > needed_close and text.endswith(")"):
            text = text[:-1]
            added_close -= 1
    else:
        while added_close > needed_close and (text.endswith("))") or text.endswith("));")):
            if text.endswith("));"):
                text = text[:-2] + ";"
            else:
                text = text[:-1]
            added_close -= 1

        # Add missing ')' if the model closed a line with ') {' or ');' but under-counted nested parens
        if 0 < added_close < needed_close:
            missing = ")" * (needed_close - added_close)
            if text.endswith(") {"):
                text = text[:-2] + missing + " {"
            elif text.endswith("){"):
                text = text[:-1] + missing + "{"
            elif text.endswith(");"):
                text = text[:-1] + missing + ";"

    return text


def clean_completion(text: str, prefix: str, suffix: str) -> str:
    if text.startswith("<|fim_middle|>"):
        text = text[len("<|fim_middle|>"):]
    if text.startswith("<fim_middle>"):
        text = text[len("<fim_middle>"):]

    for tag in ("<|fim_suffix|>", "<|fim_prefix|>", "<|fim_middle|>", "<|endoftext|>", "<?php", "?>"):
        if tag in text:
            text = text.split(tag, 1)[0]

    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1])
        elif len(lines) >= 2:
            text = "\n".join(lines[1:])

    if "\n\n" in text:
        first_part = text.split("\n\n", 1)[0]
        if first_part.strip():
            text = first_part

    text = strip_suffix_overlap(text, suffix)

    if suffix.startswith("\n") and text.endswith("\n"):
        text = text[:-1]
        if text.endswith("\r"):
            text = text[:-1]

    last_line_prefix = prefix.rsplit("\n", 1)[-1]
    if last_line_prefix and last_line_prefix.isspace() and text.startswith(last_line_prefix):
        text = text[len(last_line_prefix):]

    # Prevent duplicate quote when prefix ends with ' or " and completion starts with ' or "
    if prefix.endswith(("'", '"')) and len(text) >= 2 and text[0] == prefix[-1] and text[1].isalnum():
        text = text[1:]

    # Never allow a condition/header line (`if (...)`) to also invent the body on the next line!
    current_line_stripped = prefix.rsplit("\n", 1)[-1].lstrip()
    if (
        current_line_stripped.startswith(("if ", "if(", "elseif ", "elseif(", "} elseif", "foreach ", "foreach(", "for ", "for(", "while ", "while(", "catch ", "catch(", "} catch"))
        and "{\n" in text
    ):
        text = text.split("{\n", 1)[0] + "{"

    # Ensure enum `case Name = 'val';` has trailing semicolon if not present in suffix
    if current_line_stripped.startswith("case ") and "=" in current_line_stripped and text and not text.rstrip().endswith(";") and not suffix.lstrip(" \t").startswith(";"):
        text = text.rstrip() + ";"

    # If refactoring to `function (...) use (` and the model mistakenly used `=> expr` instead of `{ return expr; }`
    if "function" in current_line_stripped and "use (" in current_line_stripped and ") => " in text and "{" not in text:
        var_part, expr_part = text.split(") => ", 1)
        expr_clean = expr_part.rstrip("; ")
        indent = prefix.rsplit("\n", 1)[-1]
        leading_ws = indent[: len(indent) - len(indent.lstrip())]
        text = f"{var_part}) {{\n{leading_ws}    return {expr_clean};\n{leading_ws}}}"

    text = strip_prefix_repetition(text, prefix)
    text = fix_paren_and_semicolon_balance(text, prefix, suffix)

    return text


class FimProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[zed-fim-proxy] {self.address_string()} - {fmt % args}", flush=True)

    def do_POST(self):
        if not self.path.startswith("/v1/completions"):
            self.send_error(404, "Not Found")
            return

        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length)
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as e:
            self._send_json(400, {"error": f"Invalid JSON: {e}"})
            return

        auth_header = self.headers.get("Authorization", "")
        api_key = ""
        if auth_header.lower().startswith("bearer "):
            api_key = auth_header[7:].strip()
        if not api_key or api_key in ("dummy", "local"):
            api_key = ENV_API_KEY

        if not api_key:
            self._send_json(
                401,
                {"error": "Missing Gemini API key in Authorization header or GEMINI_API_KEY env"},
            )
            return

        req_model = payload.get("model", DEFAULT_GEMINI_MODEL)
        gemini_model = (
            req_model
            if req_model.startswith("gemini-3.")
            else DEFAULT_GEMINI_MODEL
        )
        prompt = payload.get("prompt", "")
        max_tokens = int(payload.get("max_tokens") or 80)

        prefix, suffix = parse_fim_prompt(prompt)

        # Pre-flight Open Semantic Slot guard (0ms, 0 tokens, zero architectural invention)
        if should_skip_request(prefix, suffix):
            response_obj = {
                "id": f"cmpl-{int(time.time() * 1000)}",
                "object": "text_completion",
                "created": int(time.time()),
                "model": req_model,
                "choices": [{"text": "", "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }
            self._send_json(200, response_obj)
            return

        user_prompt = f"<|fim_prefix|>{prefix}<|fim_suffix|>{suffix}<|fim_middle|>"

        gemini_body = {
            "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": max_tokens,
                "stopSequences": ["<|fim_suffix|>", "<|fim_prefix|>", "<|endoftext|>"],
                "thinkingConfig": {"thinkingLevel": "MINIMAL"},
            },
        }

        path = f"/v1beta/models/{gemini_model}:generateContent?key={api_key}"
        body_bytes = json.dumps(gemini_body).encode("utf-8")

        t0 = time.monotonic()
        try:
            status_code, resp_bytes = call_gemini_keepalive(path, body_bytes)
        except Exception as e:
            print(f"[zed-fim-proxy] Request error: {e}", flush=True)
            self._send_json(502, {"error": str(e)})
            return

        elapsed_ms = int((time.monotonic() - t0) * 1000)

        if status_code != 200:
            err_body = resp_bytes.decode("utf-8", errors="replace")
            print(f"[zed-fim-proxy] Gemini HTTP {status_code}: {err_body[:300]}", flush=True)
            self._send_json(status_code, {"error": err_body})
            return

        resp_data = json.loads(resp_bytes.decode("utf-8"))
        raw_text = ""
        finish_reason = "UNKNOWN"
        candidates = resp_data.get("candidates") or []
        if candidates:
            finish_reason = candidates[0].get("finishReason", "UNKNOWN")
            parts = (candidates[0].get("content") or {}).get("parts") or []
            raw_text = "".join(p.get("text", "") for p in parts if not p.get("thought"))

        completion_text = clean_completion(raw_text, prefix, suffix)

        usage_meta = resp_data.get("usageMetadata") or {}
        prompt_tokens = int(usage_meta.get("promptTokenCount") or 0)
        completion_tokens = int(usage_meta.get("candidatesTokenCount") or 0)
        total_tokens = int(
            usage_meta.get("totalTokenCount") or (prompt_tokens + completion_tokens)
        )

        try:
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as df:
                df.write(
                    json.dumps(
                        {
                            "ts": int(time.time()),
                            "latency_ms": elapsed_ms,
                            "tokens": f"{prompt_tokens}+{completion_tokens}",
                            "finish_reason": finish_reason,
                            "prefix_tail": prefix[-160:],
                            "suffix_head": suffix[:160],
                            "raw_text": raw_text,
                            "cleaned_text": completion_text,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except Exception:
            pass

        print(
            f"[zed-fim-proxy] OK model={gemini_model} latency={elapsed_ms}ms "
            f"tokens={prompt_tokens}+{completion_tokens} finish={finish_reason} "
            f"raw={raw_text[:40]!r} -> clean={completion_text[:40]!r}",
            flush=True,
        )

        response_obj = {
            "id": f"cmpl-{int(time.time() * 1000)}",
            "object": "text_completion",
            "created": int(time.time()),
            "model": req_model,
            "choices": [
                {
                    "text": completion_text,
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
        }
        self._send_json(200, response_obj)

    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), FimProxyHandler)
    print(
        f"[zed-fim-proxy] Listening on http://{HOST}:{PORT}/v1/completions (default model: {DEFAULT_GEMINI_MODEL})",
        flush=True,
    )
    server.serve_forever()
