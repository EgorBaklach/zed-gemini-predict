"""Runtime configuration (environment variables, see .env.example)."""
import os

HOST = os.environ.get("ZED_PROXY_HOST", "127.0.0.1")
PORT = int(os.environ.get("ZED_PROXY_PORT", "8089"))
DEFAULT_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
ENV_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
DEBUG_LOG_PATH = os.environ.get("ZED_PROXY_DEBUG_LOG", "/tmp/zed_fim_debug.log")
DEFAULT_MAX_TOKENS = 80
