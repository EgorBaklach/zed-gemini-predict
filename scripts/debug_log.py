#!/usr/bin/env python3
"""
Show the latest bridge decisions from the debug log: cursor line, raw Gemini answer,
what Zed received and which rules changed it.

    python3 scripts/debug_log.py              # last 15 entries
    python3 scripts/debug_log.py 40 sprintf   # last 40 entries whose cursor line contains "sprintf"
"""
import json
import os
import sys

PATH = os.environ.get("ZED_PROXY_DEBUG_LOG", "/tmp/zed_fim_debug.log")


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    needle = sys.argv[2] if len(sys.argv) > 2 else ""
    rows = [json.loads(line) for line in open(PATH, encoding="utf-8") if line.strip()]
    if needle:
        rows = [r for r in rows if needle in r["prefix_tail"].rsplit("\n", 1)[-1]]
    for r in rows[-limit:]:
        cursor_line = r["prefix_tail"].rsplit("\n", 1)[-1]
        after = r["suffix_head"].split("\n", 1)[0]
        print(f"{r['latency_ms']:4d} ms {r['tokens']:>8}  {cursor_line.strip()[-70:]!s}|{after[:25]}")
        print(f"     raw  : {r['raw_text'][:110]!r}")
        print(f"     zed  : {r['cleaned_text'][:110]!r}   rules={r.get('rules', '?')}")


if __name__ == "__main__":
    main()
