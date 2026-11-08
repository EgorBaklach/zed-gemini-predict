#!/usr/bin/env python3
"""
zed-gemini-predict - lightweight FIM-to-Gemini bridge for Zed Edit Predictions (open_ai_compatible_api).

Listens on http://127.0.0.1:8089/v1/completions and serves completions from Gemini 3.5 Flash Lite
(thinkingLevel=MINIMAL, keep-alive TLS) under the Syntactic Determinism law:

    bridge/server.py        HTTP endpoint for Zed
    bridge/fim.py           FIM prompt format
    bridge/gemini.py        Gemini client
    bridge/pipeline.py      gatekeeper -> Gemini -> ordered rules -> fallback
    bridge/rules_common.py  language-agnostic rules
    bridge/php/             PHP profile: prompt, gatekeeper, rules (+ their order), fallback

Standard library only. This file is the entry point used by systemd.
"""
from bridge.server import main

if __name__ == "__main__":
    main()
