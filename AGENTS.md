# AGENTS.md — zed-gemini-predict

Contract for an AI agent working on this repository. Read it fully before changing anything.
User communication language: **Russian**. Code, comments, docstrings, commit messages: **English**.

---

## 1. What this project is

A lightweight local HTTP bridge between **Zed Edit Predictions** (`"provider": "open_ai_compatible_api"`)
and **Google Gemini** (`gemini-3.5-flash-lite`, `thinkingLevel: MINIMAL`).
Zed sends a FIM prompt (`<|fim_prefix|>…<|fim_suffix|>…<|fim_middle|>`, `prompt_format: "qwen"`) to
`http://127.0.0.1:8089/v1/completions`; the bridge answers with a completion in OpenAI `text_completion` format.

**Main law — Syntactic Determinism (target language: modern PHP 8.2/8.3+, pure PHP, no frameworks):**
the bridge is a *syntax closer*, not Copilot. It finishes what the developer already started
(conditions, calls, brackets, `;`, `try/catch` skeleton, `fn` ↔ `function () use ()` refactoring, enum cases,
array items) and **never invents architecture or business logic** (new conditions, methods, dependencies,
classes, statements). Where any suggestion would be a guess — an **Open Semantic Slot** (blank line, bare `if (`,
`$x = `, `$this->`, cursor inside a word, …) — it must stay **silent** (empty answer, 0 tokens).

> **Silence beats wrong code.** If in doubt, return `""`.

Other languages are explicitly out of scope until the user asks (architecture is ready for them, see §4).

---

## 2. Environment (critical — read before running anything)

Host: Windows 11 laptop, 8 GB RAM, PowerShell. Runtime: **WSL 2 Ubuntu**. Rules from the user's global profile:

| Rule | Why |
|---|---|
| **Never run `python`/`python3`/`pip` on Windows.** Always `wsl python3 …` | Windows has only Store stubs that hang |
| Docker only inside WSL (`wsl docker …`) | not installed on host (not needed here anyway) |
| npm/npx on Windows only as `npm.cmd`/`npx.cmd` | `.ps1` execution policy (not needed here) |
| Keep RAM usage low, don't start parallel heavy processes | 8 GB RAM |

Practical pitfalls learned the hard way:
- **PowerShell mangles nested quotes** in `wsl bash -lc "…"`. For anything non-trivial write a `.sh`/`.py` file
  and run `wsl bash /mnt/c/.../script.sh`. Unix tools (`tail`, `grep`) don't exist in PowerShell.
- **PowerShell `Set-Content -Encoding UTF8` adds a BOM.** Don't edit repo files via PowerShell text cmdlets;
  use the file-editing tools. `.gitattributes` forces `eol=lf` (scripts run in WSL; CRLF breaks shebangs).
- Windows `C:\Users\egorb\…` = WSL `/mnt/c/Users/egorb/…`.
- Tools in WSL: Python 3.10 (stdlib only is used), PHP 8.4 CLI (needed by the emulator), git, systemd user services.

---

## 3. Where everything lives

| What | Location |
|---|---|
| **Working copy (edit here, commit & push from here)** | `C:\Users\egorb\zed-gemini-predict` (Windows git, HTTPS + credential manager) |
| **Runtime clone (systemd runs this)** | WSL `~/zed-gemini-predict` |
| GitHub | https://github.com/EgorBaklach/zed-gemini-predict (branch `main`) |
| systemd user unit | WSL `~/.config/systemd/user/zed-fim-proxy.service` (= repo `systemd/zed-fim-proxy.service`) |
| Secrets | WSL `~/.zed_fim_proxy.env` (`chmod 600`): `GEMINI_API_KEY`, `GEMINI_MODEL`. **Never print, log or commit the key.** |
| Debug log (JSONL, one line per request: `decision` = `local` / `skip` / `llm`) | WSL `/tmp/zed_fim_debug.log` (wiped on WSL restart); view with `scripts/debug_log.py` |
| Service log | `journalctl --user -u zed-fim-proxy.service` |
| Emulator output project | WSL `/tmp/zed_mvc_calc` |
| Zed config | `C:\Users\egorb\AppData\Roaming\Zed\settings.json` → `edit_predictions.open_ai_compatible_api` (`api_url`, `model`, `prompt_format: "qwen"`, `max_output_tokens: 80`, `prediction_debounce: 400`). `show_edit_predictions` is the user's choice — don't change it without asking. |

**Git from WSL cannot push** (the WSL SSH key is a deploy key of another repo → "Permission denied"). Push only
from the Windows working copy. Sync the runtime clone afterwards:
```bash
wsl bash -lc 'cd ~/zed-gemini-predict && git fetch -q origin && git reset -q --hard origin/main && chmod +x zed_fim_proxy.py && systemctl --user restart zed-fim-proxy.service'
```
(`core.fileMode=false` is set in the runtime clone.)

---

## 4. Architecture

```
Zed ──POST /v1/completions──> bridge/server.py
                                 │ parse FIM (fim.py), resolve API key/model
                                 ├─ PROFILE.local_completion(prefix, suffix) → deterministic answer, 0 tokens [php/local.py]
                                 ├─ PROFILE.should_skip(prefix, suffix)  → "" in ~2 ms, 0 tokens   [php/gatekeeper.py]
                                 ├─ GeminiClient.generate(...)           → raw text (~600 ms)      [gemini.py]
                                 ├─ postprocess(raw, prefix, suffix)     → ordered rules + trace   [pipeline.py]
                                 │     └─ if empty: PROFILE.fallback     → mechanical ")" closure  [php/fallback.py]
                                 └─ debug log line {decision: local|skip|llm, raw_text, cleaned_text, rules} + JSON response
```

| File | Responsibility |
|---|---|
| `zed_fim_proxy.py` | Entry point for systemd only (`from bridge.server import main`) |
| `bridge/config.py` | Env vars: `ZED_PROXY_HOST/PORT`, `GEMINI_MODEL`, `GEMINI_API_KEY`, `ZED_PROXY_DEBUG_LOG` |
| `bridge/server.py` | HTTP handler, auth (Bearer from Zed unless `dummy`/`local` → env key), response, debug log |
| `bridge/fim.py` | FIM tags, `parse_fim_prompt` (qwen / starcoder / codestral formats), `STOP_SEQUENCES` |
| `bridge/gemini.py` | Keep-alive TLS client, request body (`temperature 0`, `thinkingLevel MINIMAL`), reply parsing |
| `bridge/pipeline.py` | `LanguageProfile` + `postprocess()` → `(text, applied_rule_names)` |
| `bridge/rules_common.py` | Language-agnostic rules |
| `bridge/textutil.py` | `current_line`, `suffix_same_line`, `next_code_line` |
| `bridge/php/__init__.py` | **PHP profile and the ORDER of rules** (the single source of truth) |
| `bridge/php/prompt.py` | `SYSTEM_INSTRUCTION` |
| `bridge/php/gatekeeper.py` | `OPEN_SEMANTIC_SLOT_RE` + `should_skip_request` |
| `bridge/php/rules.py` | PHP rules (guards, idioms, `balance_parens`) |
| `bridge/php/syntax.py` | String-aware helpers: `paren_depth`, `without_strings`, header regexes |
| `bridge/php/fallback.py` | `mechanical_paren_closure` |
| `bridge/php/local.py` | `close_open_block`: deterministic `}` for a block whose body is written but closer is missing (braces + indentation) |

Rule contract: `rule(text, prefix, suffix) -> str`, pure, must keep `""` as `""`, named after what it does
(the name appears in the debug log). New language = new package `bridge/<lang>/` with its own profile reusing
`rules_common`. There is no language detection yet (Zed's prompt has no file path); `server.py` uses the PHP profile.

Performance is a non-issue: local processing ≈ 30 µs per request, RSS ≈ 11 MB. Latency and cost are Gemini.

---

## 5. Decision guide: where does a fix belong?

When the bridge misbehaves, choose the layer in this order of preference:

0. **Local completion** (`php/local.py`) — the correct answer is fully determined by structure alone
   (e.g. a block with a written body and a missing `}` while the next code is back at the `{` level).
   Answer without Gemini: 0 tokens, ~1 ms, deterministic. It runs BEFORE the gatekeeper (it applies exactly
   where the gatekeeper is silent), so it must be strict: verify it never fires on well-formed code
   (run it over every context in the debug log and the emulator — zero false positives expected).
1. **Gatekeeper** (`php/gatekeeper.py`) — the cursor position itself means "no suggestion possible"
   (Open Semantic Slot, line already complete with `;` / `{` / `'k' => $v,`, cursor inside an identifier).
   Cheapest: no tokens, no latency, no nondeterminism.
2. **Structural rule** (`php/rules.py` / `rules_common.py`) — Gemini's answer violates a *structural* property
   that can be checked without understanding business meaning: invented body after a header, invented call in a
   fluent chain that continues below, `;` inside `match`, duplicate of the suffix, unbalanced parens, debris
   (`)</table>`, `<?php`), echo of the previous argument. Rules must be general (structure), not tuned to one test string.
3. **Fallback** — only purely mechanical insertions (closing parens) when Gemini returned nothing.
4. **Prompt** (`php/prompt.py`) — last resort, and only *positive, scoped* guidance.
   ⚠️ Lessons: negative keyword lists ("never after `=`, `return`, `if (`") made the model over-inhibit and stop
   writing `return` in closures. A broad rule ("at a new argument position supply the next argument") leaked into
   declarations (`getHistory(` → `);`); it had to be narrowed to "after `, ` inside a CALL".
   **Any prompt change requires a full regression** (§6), because it shifts answers everywhere.

Never "fix" a problem by inventing content in Python (e.g. adding a guessed return type). Reject or stay silent.

---

## 6. Workflow for any change

1. Reproduce: find the case in the debug log (`wsl python3 /mnt/c/Users/egorb/zed-gemini-predict/scripts/debug_log.py 30 <text>`);
   the `rules` field tells which rules already touched the answer.
2. Add the **real raw Gemini answer + exact context** as a case to `tests/test_postprocessor_offline.py`
   (and a `RULE_TRACE_CASES` entry if a new rule is introduced).
3. Implement in the right layer (§5). New rule → function with docstring in `rules.py` / `rules_common.py`
   **and** insert it at the right position in `RULES` in `bridge/php/__init__.py` (order matters: debris cleanup →
   fit to suffix/prefix → invention guards → formatting/idioms → final line consistency, `balance_parens` last).
4. Offline tests (free, instant):
   `wsl python3 /mnt/c/Users/egorb/zed-gemini-predict/tests/test_postprocessor_offline.py` → must be all ✅.
5. Deploy to the running service: `wsl bash /mnt/c/Users/egorb/zed-gemini-predict/scripts/deploy_wsl.sh`
   (the startup log line shows the number of rules).
6. Live regression: `wsl bash /mnt/c/Users/egorb/zed-gemini-predict/scripts/regression.sh` (emulator ×3).
   For a targeted check: `simulate_mvc_live_coding.py --only slot_a,slot_b --runs 3`.
7. Update README if behaviour/structure changed, commit from Windows, push, sync the runtime clone (§3).

For pure refactors: prove equivalence with a differential test (old module vs new code on every
context × raw answer combination from the debug log and the emulator) before running live tests.

---

## 7. Tests

| Test | Needs | Cost | What it proves |
|---|---|---|---|
| `tests/test_postprocessor_offline.py` | nothing | 0 tokens, <1 s | gatekeeper, every rule, rule trace, fallback on **real captured raw answers** |
| `tests/simulate_mvc_live_coding.py` | running bridge + `php` | ~30k tokens/session, ~40 s | **main integration test**: types an 8-file OOP MVC calculator (Enum, Interface, Trait, Model, fluent Builder, View, Controller, index.php) "inside Zed": 27 probes must be silent, 25 Alt+\ slots validated by regex/paren balance/duplicate checks, a Tab re-request after every accepted answer, then `php -l` on all files and 16 runtime assertions. Covers all cases D1–D26, P1–P16, P83-17..20 + real Zed traps ZED-1..8 |
| `tests/test_determinism.py` | running bridge | small | 16 open slots must return `''`, 10 deterministic cases must return code |
| `tests/test_php_cases.py`, `tests/test_php83_cases.py` | running bridge | small | print answers for eyeball review (no assertions) |

**Gemini is nondeterministic even at `temperature 0`.** A single green run proves little — use `--runs 3`.
Healthy baseline: every run `php -l` OK + 16/16 runtime, 27/27 probes silent,
23–25/25 slots, post-Tab silent ~24/24. Known non-blocking misses are listed in §9.

Emulator template syntax: `⟦name⟧` = completion slot (`SLOTS`: `golden`, `expect` regex, optional `apply=False`),
`⟦?name⟧` = probe (`PROBES`: `typed`, optional `after` = text auto-inserted by Zed after the cursor).
Everything above the cursor contains the bridge's real accepted answers; below the cursor is existing code.

---

## 8. Zed behaviour you must know

- Predictions are requested on `Alt+\` (or automatically if the user enabled `show_edit_predictions`).
  Once a prediction is active, Zed **re-requests on every keystroke and right after Tab** (debounce 400 ms).
  Hence the gatekeeper's "line already complete" checks and the emulator's post-Tab check.
- Zed auto-closes brackets/quotes: a probe like `$payload = [` arrives with suffix `];`, `'` with suffix `'`.
- `prompt_format: "qwen"` → `<|fim_prefix|>`/`<|fim_suffix|>`/`<|fim_middle|>`; Zed sends ~500–1000 tokens of context.
- **FIM answers are inserted AT THE CURSOR only** (no edits elsewhere; that would need Zed's `zeta` formats).
  Example: after moving a one-line `if` body under a new `{` and pressing Tab, the cursor is *before* the body —
  a `}` after the body cannot be offered there. At the end of the body line (End) `close_open_block` offers `\n    }`.

Historical decisions (don't regress): `gemini-2.5-flash-lite` is retired for new keys (404) → `gemini-3.5-flash-lite`;
`thinkingBudget: 0` → 400 on 3.5, use `thinkingLevel: "MINIMAL"`; `<|fim_middle|>` must NOT be a stop sequence
(Gemini echoes it first → empty answer), it is stripped by `strip_fim_tags` instead.

---

## 9. Known limitations / open topics

- `sprintf('%s %s %s = %s', $a, $op->value, $b, |` → Flash Lite tends to answer `$b` (argument echo);
  `reject_argument_echo` turns this into silence. A correct `$result` appears only sometimes.
- Interface signature `getHistory(|` occasionally gets `);` (valid PHP, missing return type). The bridge must not add types itself.
- After Tab on an array item before `];` the model may add a trailing `,` — valid PHP, reported by the emulator as a warning.
- Not yet explored: trimming the context Zed sends (fewer tokens/lower latency vs. losing patterns above the cursor).
  Must be measured with the emulator (`--runs 3`) for quality, latency and tokens before adopting.

---

## 10. Don'ts

- No third-party dependencies (stdlib only, Python 3.10), no Docker for the bridge, no async rewrite, no plugin frameworks.
- No Bitrix/Laravel/Go specifics — pure PHP only, unless the user asks.
- Don't loosen emulator validators to make a run green unless the answer is genuinely valid PHP
  (e.g. non-capturing `catch (\Throwable)` was a legitimate validator fix).
- Don't change the prompt and rules in the same step without a regression in between — you won't know which one helped.
- Don't commit secrets, `/tmp` artifacts or `__pycache__`; don't push from WSL.
