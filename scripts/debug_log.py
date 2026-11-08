#!/usr/bin/env python3
"""
Show the latest bridge decisions from the debug log.

Each request is one of:
  llm   - Gemini answered: raw answer, what Zed received, which rules changed it
  local - deterministic answer computed without Gemini (e.g. closing a block)
  skip  - gatekeeper decided to stay silent (Open Semantic Slot / finished line)

    python3 scripts/debug_log.py               # last 15 entries
    python3 scripts/debug_log.py 40 sprintf    # last 40 entries whose cursor line contains "sprintf"
    python3 scripts/debug_log.py 40 "" llm     # only Gemini calls
"""
import json
import os
import sys

PATH = os.environ.get("ZED_PROXY_DEBUG_LOG", "/tmp/zed_fim_debug.log")


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    needle = sys.argv[2] if len(sys.argv) > 2 else ""
    only = sys.argv[3] if len(sys.argv) > 3 else ""
    rows = [json.loads(line) for line in open(PATH, encoding="utf-8") if line.strip()]
    for r in rows:
        r.setdefault("decision", "llm")  # entries written before decisions were logged
    if needle:
        rows = [r for r in rows if needle in r["prefix_tail"].rsplit("\n", 1)[-1]]
    if only:
        rows = [r for r in rows if r["decision"] == only]
    for r in rows[-limit:]:
        cursor_line = r["prefix_tail"].rsplit("\n", 1)[-1]
        after = r["suffix_head"].split("\n", 1)[0]
        cost = f"{r.get('latency_ms', 0):4d} ms {r.get('tokens', '0+0'):>8}" if r["decision"] == "llm" else " " * 16
        print(f"[{r['decision']:5}] {cost}  {cursor_line.rstrip()[-70:]}|{after[:25]}")
        if r["decision"] == "llm":
            print(f"        raw : {r['raw_text'][:110]!r}")
        if r["decision"] != "skip":
            print(f"        zed : {r['cleaned_text'][:110]!r}   rules={r.get('rules', [])}")


if __name__ == "__main__":
    main()
