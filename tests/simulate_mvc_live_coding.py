#!/usr/bin/env python3
"""
Live-coding emulator: an OOP MVC Calculator in modern PHP 8.2+/8.3+ written "inside Zed"
against the running zed-gemini-predict bridge.

How the emulation works
-----------------------
* The project is described as 8 PHP file templates (Enum, Interface, Trait, Model, Builder,
  View, Controller, front controller index.php). Each template contains cursor markers:
    ⟦name⟧   - COMPLETION slot: the developer stops here and presses Alt+\\.
               The bridge MUST return valid, minimal syntax closure (checked by validators).
    ⟦?name⟧  - PROBE: the developer is in the middle of typing (`if (`, `$x = `, `$this->`, ...).
               The bridge MUST stay silent ('' with 0 tokens) - an "Open Semantic Slot".
* Files are "typed" top-to-bottom: everything ABOVE the cursor contains the bridge's real,
  already-accepted answers; everything BELOW the cursor is code that already exists.
* After every accepted completion the emulator presses Tab: the answer is inserted and the
  request is re-sent from the new cursor position (exactly what Zed does after ~400 ms).
  The bridge should stay silent there instead of inventing the next statement.
* Finally the project is assembled from the bridge's answers into /tmp/zed_mvc_calc,
  every file is checked with `php -l`, and index.php is executed with runtime assertions.

The scenario covers every case from test_determinism.py (D1-D26), test_php_cases.py (P1-P16),
test_php83_cases.py (P83-17..20) plus real traps captured from /tmp/zed_fim_debug.log (ZED-*).

Usage (inside WSL):
    python3 tests/simulate_mvc_live_coding.py [--runs N] [--verbose]
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

PROXY_URL = os.environ.get("ZED_PROXY_URL", "http://127.0.0.1:8089/v1/completions")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
OUT_DIR = "/tmp/zed_mvc_calc"
MARKER_RE = re.compile(r"⟦(\?)?(\w+)⟧")
SENTINEL = "\x00"


# ─────────────────────────────────────────────────────────────────────────────
# Bridge client
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Answer:
    text: str
    ms: int
    prompt_tokens: int
    completion_tokens: int

    @property
    def local(self) -> bool:
        """True when the bridge answered from its pre-flight gatekeeper without calling Gemini."""
        return self.prompt_tokens == 0


def query(prefix: str, suffix: str) -> Answer:
    prompt = f"<|fim_prefix|>{prefix}<|fim_suffix|>{suffix}<|fim_middle|>"
    body = json.dumps({"model": MODEL, "prompt": prompt, "max_tokens": 80}).encode("utf-8")
    req = urllib.request.Request(
        PROXY_URL, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    ms = int((time.monotonic() - t0) * 1000)
    usage = data.get("usage") or {}
    return Answer(
        text=data["choices"][0]["text"],
        ms=ms,
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Completion slots (developer presses Alt+\ and expects minimal syntax closure)
#   expect  - regex that the stripped answer must fully match
#   golden  - reference text used while the slot is still BELOW the cursor
#   apply   - insert the bridge answer into the final project (False = validate only)
# ─────────────────────────────────────────────────────────────────────────────
SLOTS = {
    # Operation.php
    "enum_case": dict(
        title="Backed Enum: `case Divide = |`",
        covers=["D19", "P83-17"], golden="'/';", expect=r"'/'\s*;",
    ),
    "enum_label_last": dict(
        title="match($this) in enum: last arm `self::Modulo => |`",
        covers=["P83-17", "P15"], golden="'Остаток',", expect=r"'[^'\n]+',?",
    ),
    # CalculatorInterface.php
    "iface_signature": dict(
        title="Interface signature: `public function getHistory(|`",
        covers=["P8"], golden="): array;", expect=r"\)\s*:\s*\??(array|iterable)\s*;",
    ),
    # HistoryTrait.php
    "trait_getter": dict(
        title="Trait getter return type from `private array $history`",
        covers=["D25", "P83-18"], golden="): array", expect=r"\)\s*:\s*array",
    ),
    "trait_arrow_filter": dict(
        title="array_filter + fn(): bool => | before `));`",
        covers=["P13"], golden="$r > 0", expect=r"\$r\s*>\s*0(\.0)?",
    ),
    # CalculatorModel.php
    "model_implements": dict(
        title="`final class CalculatorModel implements |`",
        covers=["P7"], golden="CalculatorInterface", expect=r"CalculatorInterface",
    ),
    "model_if_close": dict(
        title="Close `if ($op === Operation::Divide && $b === 0.0|` without new &&",
        covers=["D21", "P1"], golden=") {", expect=r"\)\s*\{",
    ),
    "model_match_last": dict(
        title="match arm `Operation::Modulo => |`",
        covers=["P15"], golden="fmod($a, $b),", expect=r"(fmod\(\$a,\s*\$b\)|\$a\s*%\s*\$b),?",
    ),
    "model_sprintf": dict(
        title="Nested sprintf() inside remember() with `, $result);` on the same line",
        covers=["P12", "D22"], golden="$result)", expect=r"\$result\)",
    ),
    "model_filter_refactor": dict(
        title="Refactor fn() => into function () use (|) { return ...; }",
        covers=["D23", "P3"], golden="$min): bool { return $r >= $min; }",
        expect=r"\$min\)(\s*:\s*bool)?\s*\{\s*return\s+\$r\s*>=\s*\$min;\s*\}",
    ),
    "model_round_refactor": dict(
        title="Reverse refactor function () use () into fn() => |",
        covers=["D24", "P4"], golden="round($r, $precision)", expect=r"round\(\$r,\s*\$precision\)",
    ),
    # CalculatorView.php
    "view_sprintf": dict(
        title="sprintf() pattern continuation `$this->fmt($b), |`",
        covers=["P12"], golden="$this->fmt($result));", expect=r"\$this->fmt\(\$result\)\);",
    ),
    "view_array_item": dict(
        title="Array item `'error' => |` before `];`",
        covers=["D20", "P2"], golden="$error,", expect=r"\$error,?",
    ),
    "view_json_flags": dict(
        title="json_encode flags `JSON_THROW_ON_ERROR | |`",
        covers=["D26", "P14"], golden="JSON_UNESCAPED_UNICODE);",
        expect=r"JSON_[A-Z_]+(\s*\|\s*JSON_[A-Z_]+)*\);",
    ),
    "view_match_default": dict(
        title="match default arm `default => |`",
        covers=["P15"], golden="'Unknown',", expect=r"'[^'\n]*',?",
    ),
    # CalculatorController.php
    "ctrl_ctor": dict(
        title="Constructor promotion `private readonly |`",
        covers=["P9"], golden="CalculatorView $view,", expect=r"CalculatorView \$view,?",
    ),
    "ctrl_validate": dict(
        title="Deeply nested validation `... || !is_numeric($request['b']|`",
        covers=["D21", "P1"], golden=")) {", expect=r"\)\)\s*\{",
    ),
    "ctrl_nullsafe": dict(
        title="Nullsafe chain `Operation::tryFrom(...)?->label(|`",
        covers=["P83-20"], golden=");", expect=r"\)(\s*\?\?\s*(null|'[^'\n]*'))?;",
    ),
    "ctrl_catch": dict(
        title="`} catch (|`",
        covers=["D17", "P5"], golden="\\Throwable $e) {",
        expect=r"\\?[A-Za-z\\]+(\s*\|\s*\\?[A-Za-z\\]+)*\s+\$e\)\s*\{",
    ),
    "ctrl_foreach": dict(
        title="foreach key => value `as $index => |`",
        covers=["P10"], golden="$entry) {", expect=r"\$entry\)\s*\{",
    ),
    "ctrl_try_skeleton": dict(
        title="Bare `try {` without catch below -> minimal skeleton",
        covers=["D18", "P6"], apply=False,
        golden=(
            "\n            return $this->history();"
            "\n        } catch (\\Throwable $e) {"
            "\n            return $e->getMessage();"
            "\n        }"
        ),
        expect=r".*\}\s*catch\s*\(\s*\\?[A-Za-z\\|]+(\s+\$\w+)?\s*\)\s*\{.*\}",  # PHP 8 allows `catch (\Throwable)`
    ),
    "ctrl_for": dict(
        title="Classic for counter `for ($i = 1; $i <= $count; |`",
        covers=["P11"], golden="$i++) {", expect=r"(\$i\+\+|\+\+\$i)\)\s*\{",
    ),
    # index.php
    "idx_concat": dict(
        title="Concatenation `rtrim(...) . '/src/' . ltrim($relative|` before ` . '.php';`",
        covers=["D22", "P16"], golden=", '/')", expect=r"(,\s*'/'\s*)?\)",
    ),
    "idx_fluent": dict(
        title="Fluent builder chain `->withOp(Operation::Divide|` before `->build();`",
        covers=["P83-19"], golden=")", expect=r"\)",
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# Probes (developer is mid-typing - the bridge MUST stay silent)
#   typed - text typed at the cursor, after - text auto-inserted by Zed after the cursor
# ─────────────────────────────────────────────────────────────────────────────
PROBES = {
    "p_enum_blank": dict(title="Blank line inside enum", covers=["D1"], typed=""),
    "p_static": dict(title="`return self::` (waiting for LSP)", covers=["D14"], typed="return self::"),
    "p_prop_assign": dict(title="`$this->history[] = ` (empty RHS)", covers=["D9"], typed="$this->history[] = "),
    "p_blank_class": dict(title="Blank line inside class body", covers=["D1"], typed=""),
    "p_pubfn": dict(title="`public function ` without name", covers=["D16"], typed="public function "),
    "p_if": dict(title="Bare `if (` with auto-closed `)`", covers=["D3"], typed="if (", after=")"),
    "p_throw": dict(title="`throw new ` without class", covers=["D15"], typed="throw new "),
    "p_match": dict(title="`$result = match (` without subject", covers=["D7"], typed="$result = match (", after=")"),
    "p_member": dict(title="`$this->` (waiting for LSP)", covers=["D12"], typed="$this->"),
    "p_clone_assign": dict(title="`$clone->data['b'] = ` (empty RHS)", covers=["D8", "D9"], typed="$clone->data['b'] = "),
    "p_clone_member": dict(title="`$clone->data['op'] = $op->`", covers=["D12"], typed="$clone->data['op'] = $op->"),
    "p_assign": dict(title="`$formatted = ` (empty RHS)", covers=["D8"], typed="$formatted = "),
    "p_dollar": dict(title="Bare `$` with `formatted` right of cursor", covers=["ZED-1"], typed="$", after="formatted"),
    "p_while": dict(title="Bare `while (`", covers=["D5"], typed="while (", after=")"),
    "p_empty_array": dict(title="`$payload = [` with auto-closed `];`", covers=["ZED-2"], typed="$payload = [", after="];"),
    "p_quote": dict(title="Bare `'` with auto-closed `'` inside array", covers=["ZED-3"], typed="'", after="'"),
    "p_coalesce": dict(title="`$payload['error'] ??= ` (empty RHS)", covers=["D10"], typed="$payload['error'] ??= "),
    "p_brace": dict(title="Line with a bare `{`", covers=["D2"], typed=""),
    "p_comment": dict(title="Comment line `// `", covers=["D16"], typed="// "),
    "p_cyrillic": dict(title="Wrong keyboard layout `ша()`", covers=["ZED-4"], typed="ша()"),
    "p_elseif": dict(title="Bare `} elseif (`", covers=["D4"], typed=" elseif (", after=") {\n        }"),
    "p_nullsafe_member": dict(title="`$x = Operation::tryFrom('+')?->`", covers=["D13"], typed="$x = Operation::tryFrom('+')?->"),
    "p_midword": dict(title="Cursor inside identifier `$this->mod|el`", covers=["ZED-5"], typed="$this->mod", after="el"),
    "p_partial_kw": dict(title="Half-typed keyword `fo`", covers=["ZED-6"], typed="fo"),
    "p_foreach": dict(title="Bare `foreach (`", covers=["D6"], typed="foreach (", after=")"),
    "p_new": dict(title="`$model = new ` without class", covers=["D11"], typed="$model = new "),
}

# ─────────────────────────────────────────────────────────────────────────────
# Project templates (typed in this order)
# ─────────────────────────────────────────────────────────────────────────────
FILES = [
    ("src/Models/Operation.php", "Enum", r"""<?php
declare(strict_types=1);

namespace App\Models;

enum Operation: string
{
    case Add = '+';
    case Subtract = '-';
    case Multiply = '*';
    case Divide = ⟦enum_case⟧
    case Modulo = '%';
    ⟦?p_enum_blank⟧

    public function label(): string
    {
        return match ($this) {
            self::Add => 'Сложение',
            self::Subtract => 'Вычитание',
            self::Multiply => 'Умножение',
            self::Divide => 'Деление',
            self::Modulo => ⟦enum_label_last⟧
        };
    }

    public static function fallback(): self
    {
        ⟦?p_static⟧
        return self::Add;
    }
}
"""),
    ("src/Contracts/CalculatorInterface.php", "Interface", r"""<?php
declare(strict_types=1);

namespace App\Contracts;

use App\Models\Operation;

interface CalculatorInterface
{
    public function calculate(float $a, float $b, Operation $op): float;

    /** @return list<string> */
    public function getHistory(⟦iface_signature⟧
}
"""),
    ("src/Traits/HistoryTrait.php", "Trait", r"""<?php
declare(strict_types=1);

namespace App\Traits;

trait HistoryTrait
{
    /** @var list<string> */
    private array $history = [];

    /** @var list<float> */
    private array $results = [];

    protected function remember(string $entry, float $result): void
    {
        ⟦?p_prop_assign⟧
        $this->history[] = $entry;
        $this->results[] = $result;
    }

    /** @return list<string> */
    public function getHistory(⟦trait_getter⟧
    {
        return $this->history;
    }

    /** @return list<float> */
    public function positiveResults(): array
    {
        return array_values(array_filter($this->results, fn(float $r): bool => ⟦trait_arrow_filter⟧));
    }
}
"""),
    ("src/Models/CalculatorModel.php", "Model", r"""<?php
declare(strict_types=1);

namespace App\Models;

use App\Contracts\CalculatorInterface;
use App\Traits\HistoryTrait;

final class CalculatorModel implements ⟦model_implements⟧
{
    use HistoryTrait;
    ⟦?p_blank_class⟧
    ⟦?p_pubfn⟧

    public function calculate(float $a, float $b, Operation $op): float
    {
        ⟦?p_if⟧
        if ($op === Operation::Divide && $b === 0.0⟦model_if_close⟧
            ⟦?p_throw⟧
            throw new \DivisionByZeroError('Division by zero');
        }

        ⟦?p_match⟧
        $result = match ($op) {
            Operation::Add => $a + $b,
            Operation::Subtract => $a - $b,
            Operation::Multiply => $a * $b,
            Operation::Divide => $a / $b,
            Operation::Modulo => ⟦model_match_last⟧
        };
        ⟦?p_member⟧
        $this->remember(sprintf('%s %s %s = %s', $a, $op->value, $b, ⟦model_sprintf⟧, $result);

        return $result;
    }

    /** @return array<int, float> */
    public function filterHistory(float $min): array
    {
        // return array_filter($this->results, fn(float $r): bool => $r >= $min);
        return array_filter($this->results, function (float $r) use (⟦model_filter_refactor⟧);
    }

    /** @return array<int, float> */
    public function roundedResults(int $precision): array
    {
        // return array_map(function (float $r) use ($precision) { return round($r, $precision); }, $this->results);
        return array_map(fn(float $r): float => ⟦model_round_refactor⟧, $this->results);
    }
}
"""),
    ("src/Http/RequestBuilder.php", "Builder", r"""<?php
declare(strict_types=1);

namespace App\Http;

use App\Models\Operation;

final class RequestBuilder
{
    /** @var array<string, float|string> */
    private array $data = [];

    public function withA(float $a): static
    {
        $clone = clone $this;
        $clone->data['a'] = $a;

        return $clone;
    }

    public function withB(float $b): static
    {
        $clone = clone $this;
        ⟦?p_clone_assign⟧
        $clone->data['b'] = $b;

        return $clone;
    }

    public function withOp(Operation $op): static
    {
        $clone = clone $this;
        ⟦?p_clone_member⟧
        $clone->data['op'] = $op->value;

        return $clone;
    }

    /** @return array<string, float|string> */
    public function build(): array
    {
        return $this->data;
    }
}
"""),
    ("src/Views/CalculatorView.php", "View", r"""<?php
declare(strict_types=1);

namespace App\Views;

use App\Models\Operation;

final class CalculatorView
{
    public function renderText(float $a, Operation $op, float $b, float $result): string
    {
        ⟦?p_assign⟧
        ⟦?p_dollar⟧
        ⟦?p_while⟧
        return sprintf('%s %s %s = %s', $this->fmt($a), $op->value, $this->fmt($b), ⟦view_sprintf⟧
    }

    public function renderJson(bool $success, ?float $result, ?string $error = null, int $code = 200, ?string $label = null): string
    {
        ⟦?p_empty_array⟧
        $payload = [
            'success' => $success,
            'code' => $code,
            'status' => $this->statusText($code),
            'operation' => $label,
            'result' => $result,
            ⟦?p_quote⟧
            'error' => ⟦view_array_item⟧
        ];
        ⟦?p_coalesce⟧

        return json_encode($payload, JSON_THROW_ON_ERROR | ⟦view_json_flags⟧
    }

    public function statusText(int $code): string
    {
        return match ($code) {
            200 => 'OK',
            400 => 'Bad Request',
            422 => 'Unprocessable Entity',
            default => ⟦view_match_default⟧
        };
    }

    private function fmt(float $value): string
    {
        return number_format($value, 2, '.', '');
    }
}
"""),
    ("src/Controllers/CalculatorController.php", "Controller", r"""<?php
declare(strict_types=1);

namespace App\Controllers;

use App\Models\CalculatorModel;
use App\Models\Operation;
use App\Views\CalculatorView;

final class CalculatorController
{
    public function __construct(
        private readonly CalculatorModel $model,
        private readonly ⟦ctrl_ctor⟧
    ) {}

    public function handle(array $request): string
    {⟦?p_brace⟧
        ⟦?p_comment⟧
        ⟦?p_cyrillic⟧
        if (!isset($request['a'], $request['b'], $request['op']) || !is_numeric($request['a']) || !is_numeric($request['b']⟦ctrl_validate⟧
            return $this->view->renderJson(false, null, 'Invalid input', 422);
        }⟦?p_elseif⟧

        $label = Operation::tryFrom((string) $request['op'])?->label(⟦ctrl_nullsafe⟧
        ⟦?p_nullsafe_member⟧
        ⟦?p_midword⟧

        try {
            $op = Operation::from((string) $request['op']);
            $result = $this->model->calculate((float) $request['a'], (float) $request['b'], $op);

            return $this->view->renderJson(true, $result, null, 200, $label);
        } catch (⟦ctrl_catch⟧
            return $this->view->renderJson(false, null, $e->getMessage(), 400, $label);
        }
    }

    public function history(): string
    {
        $lines = [];
        ⟦?p_partial_kw⟧
        ⟦?p_foreach⟧
        foreach ($this->model->getHistory() as $index => ⟦ctrl_foreach⟧
            $lines[] = sprintf('#%d %s', $index + 1, $entry);
        }

        return implode(PHP_EOL, $lines);
    }

    public function safeHistory(): string
    {
        try {⟦ctrl_try_skeleton⟧
    }

    public function table(int $count): string
    {
        $rows = [];
        for ($i = 1; $i <= $count; ⟦ctrl_for⟧
            $rows[] = $this->view->renderText((float) $i, Operation::Multiply, (float) $i, (float) ($i * $i));
        }

        return implode(PHP_EOL, $rows);
    }
}
"""),
    ("index.php", "Front", r"""<?php
declare(strict_types=1);

use App\Controllers\CalculatorController;
use App\Http\RequestBuilder;
use App\Models\CalculatorModel;
use App\Models\Operation;
use App\Views\CalculatorView;

spl_autoload_register(static function (string $class): void {
    $relative = str_replace('\\', '/', substr($class, strlen('App\\')));
    $file = rtrim(__DIR__, '/') . '/src/' . ltrim($relative⟦idx_concat⟧ . '.php';
    if (is_file($file)) {
        require $file;
    }
});

⟦?p_new⟧
$model = new CalculatorModel();
$view = new CalculatorView();
$controller = new CalculatorController($model, $view);

$divide = (new RequestBuilder())->withA(20)->withB(4)->withOp(Operation::Divide⟦idx_fluent⟧
    ->build();

$report = [
    'add' => json_decode($controller->handle(['a' => 10, 'b' => 5, 'op' => '+']), true),
    'divide' => json_decode($controller->handle($divide), true),
    'mod' => json_decode($controller->handle(['a' => 10, 'b' => 3, 'op' => '%']), true),
    'div_zero' => json_decode($controller->handle(['a' => 10, 'b' => 0, 'op' => '/']), true),
    'invalid' => json_decode($controller->handle(['a' => 'x', 'b' => 1, 'op' => '+']), true),
    'bad_op' => json_decode($controller->handle(['a' => 1, 'b' => 1, 'op' => '^']), true),
    'text' => $view->renderText(7, Operation::Multiply, 6, 42),
    'history' => $controller->history(),
    'safe_history' => $controller->safeHistory(),
    'table' => $controller->table(3),
    'filtered' => array_values($model->filterHistory(10.0)),
    'rounded' => $model->roundedResults(1),
    'positive' => $model->positiveResults(),
    'fallback' => Operation::fallback()->value,
];

echo json_encode($report, JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR), PHP_EOL;
"""),
]


# ─────────────────────────────────────────────────────────────────────────────
# Template rendering
# ─────────────────────────────────────────────────────────────────────────────
def split_template(tpl: str) -> list:
    parts, pos = [], 0
    for m in MARKER_RE.finditer(tpl):
        parts.append(tpl[pos:m.start()])
        name = m.group(2)
        kind = "probe" if m.group(1) else "slot"
        if kind == "slot" and name not in SLOTS:
            raise KeyError(f"Unknown slot {name}")
        if kind == "probe" and name not in PROBES:
            raise KeyError(f"Unknown probe {name}")
        parts.append((kind, name))
        pos = m.end()
    parts.append(tpl[pos:])
    return parts


def render(parts: list, filled: dict) -> str:
    out = []
    for p in parts:
        if isinstance(p, str):
            out.append(p)
        elif p[0] == "probe":
            out.append(SENTINEL)
        else:
            spec = SLOTS[p[1]]
            if spec.get("apply", True) and p[1] in filled:
                out.append(filled[p[1]])
            else:
                out.append(spec["golden"])
    text = "".join(out)
    text = re.sub(rf"^[ \t]*{SENTINEL}\n", "", text, flags=re.M)  # own-line probes vanish
    return text.replace(SENTINEL, "")


def cursor_context(parts: list, idx: int, filled: dict) -> tuple[str, str]:
    """prefix = code above the cursor (with real accepted answers), suffix = existing code below."""
    before = render(parts[:idx], filled)
    after = render(parts[idx + 1:], {})
    return before, after


# ─────────────────────────────────────────────────────────────────────────────
# Validators
# ─────────────────────────────────────────────────────────────────────────────
def _strip_php_strings(s: str) -> str:
    return re.sub(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"", "''", s)


def generic_problems(text: str, prefix: str, suffix: str) -> list[str]:
    problems = []
    for art in ("<|", "```", "<?php", "?>"):
        if art in text:
            problems.append(f"artifact {art!r}")
    cur_line = prefix.rsplit("\n", 1)[-1]
    suf_line = suffix.split("\n", 1)[0]
    region = _strip_php_strings(cur_line + text + suf_line)
    if region.count("(") != region.count(")"):
        problems.append(f"unbalanced () {region.count('(')}:{region.count(')')}")
    if region.count("[") != region.count("]"):
        problems.append(f"unbalanced [] {region.count('[')}:{region.count(']')}")
    stripped = text.strip()
    if suf_line.strip() and len(suf_line.strip()) >= 2 and stripped.endswith(suf_line.strip()):
        problems.append(f"duplicates same-line suffix {suf_line.strip()!r}")
    next_line = next((l.strip() for l in suffix.split("\n")[1:] if l.strip()), "")
    if len(next_line) >= 3 and stripped.endswith(next_line):
        problems.append(f"duplicates next suffix line {next_line!r}")
    if len(stripped) >= 4 and cur_line.strip().endswith(stripped):
        problems.append("echoes the prefix")
    return problems


# ─────────────────────────────────────────────────────────────────────────────
# Runtime assertions for the assembled calculator
# ─────────────────────────────────────────────────────────────────────────────
def runtime_checks(r: dict) -> list[tuple[str, bool]]:
    def chk(fn):
        try:
            return bool(fn())
        except Exception:
            return False

    return [
        ("10 + 5 = 15", chk(lambda: r["add"]["success"] is True and r["add"]["result"] == 15)),
        ("20 / 4 = 5 via fluent RequestBuilder", chk(lambda: r["divide"]["result"] == 5)),
        ("10 % 3 = 1", chk(lambda: r["mod"]["result"] == 1)),
        ("10 / 0 -> 'Division by zero' (400)", chk(lambda: r["div_zero"]["success"] is False
                                                   and "Division by zero" in r["div_zero"]["error"]
                                                   and r["div_zero"]["code"] == 400)),
        ("invalid input -> 422 'Unprocessable Entity'", chk(lambda: r["invalid"]["code"] == 422
                                                            and r["invalid"]["status"] == "Unprocessable Entity")),
        ("unknown op '^' -> ValueError caught (400)", chk(lambda: r["bad_op"]["success"] is False
                                                          and r["bad_op"]["code"] == 400)),
        ("nullsafe label = 'Сложение'", chk(lambda: r["add"]["operation"] == "Сложение")),
        ("renderText = '7.00 * 6.00 = 42.00'", chk(lambda: r["text"] == "7.00 * 6.00 = 42.00")),
        ("history() has 3 lines incl. '#2 20 / 4 = 5'", chk(lambda: len(r["history"].splitlines()) == 3
                                                            and "#2 20 / 4 = 5" in r["history"])),
        ("safeHistory() == history()", chk(lambda: r["safe_history"] == r["history"])),
        ("table(3) multiplication rows", chk(lambda: r["table"].splitlines() == [
            "1.00 * 1.00 = 1.00", "2.00 * 2.00 = 4.00", "3.00 * 3.00 = 9.00"])),
        ("filterHistory(10) == [15]", chk(lambda: r["filtered"] == [15])),
        ("roundedResults(1) == [15, 5, 1]", chk(lambda: r["rounded"] == [15, 5, 1])),
        ("positiveResults() == [15, 5, 1]", chk(lambda: r["positive"] == [15, 5, 1])),
        ("Operation::fallback() == '+'", chk(lambda: r["fallback"] == "+")),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Emulation
# ─────────────────────────────────────────────────────────────────────────────
def short(s: str, n: int = 70) -> str:
    r = repr(s)
    return r if len(r) <= n else r[: n - 3] + "...'"


def run_once(verbose: bool, only: set | None = None) -> dict:
    filled: dict[str, str] = {}
    steps = []
    n = 0

    for path, layer, tpl in FILES:
        parts = split_template(tpl)
        print(f"\n── {layer}: {path} " + "─" * max(0, 70 - len(path) - len(layer)))
        for idx, p in enumerate(parts):
            if isinstance(p, str):
                continue
            kind, name = p
            n += 1
            if only and name not in only:
                continue
            prefix, suffix = cursor_context(parts, idx, filled)

            if kind == "probe":
                spec = PROBES[name]
                prefix += spec["typed"]
                suffix = spec.get("after", "") + suffix
                ans = query(prefix, suffix)
                ok = ans.text == ""
                where = "🔒 local" if ans.local else "LLM"
                mark = "✅" if ok else "❌"
                print(f"{mark} {n:02d} PROBE [{','.join(spec['covers'])}] {spec['title']}")
                print(f"       -> {where} {ans.ms} ms, answer {short(ans.text)}")
                steps.append(dict(n=n, kind=kind, name=name, ok=ok, local=ans.local, ms=ans.ms,
                                  tokens=ans.prompt_tokens + ans.completion_tokens, covers=spec["covers"]))
                continue

            spec = SLOTS[name]
            ans = query(prefix, suffix)
            text = ans.text
            problems = [] if text else ["empty answer"]
            if text:
                problems += generic_problems(text, prefix, suffix)
                if not re.fullmatch(spec["expect"], text.strip(), flags=re.S):
                    problems.append(f"does not match /{spec['expect']}/")
            filled[name] = text if text else spec["golden"]

            # Tab: accept the suggestion, Zed re-requests from the new cursor position.
            tab = query(prefix + text, suffix) if text else None
            tab_ok = tab is None or tab.text == ""

            ok = not problems
            mark = "✅" if ok else "❌"
            print(f"{mark} {n:02d} SLOT  [{','.join(spec['covers'])}] {spec['title']}")
            print(f"       -> LLM {ans.ms} ms (+{ans.completion_tokens} tok): {short(text, 90)}")
            if problems:
                print(f"       !! {'; '.join(problems)}")
            if tab is not None:
                if tab_ok:
                    how = "🔒 local" if tab.local else "LLM said ''"
                    print(f"       Tab -> silent ({how}, {tab.ms} ms)")
                else:
                    print(f"       Tab -> ⚠️ keeps writing ({tab.ms} ms): {short(tab.text, 80)}")
            if verbose:
                print(f"       prefix…{short(prefix[-80:], 100)}")
                print(f"       suffix {short(suffix[:60], 80)}…")
            steps.append(dict(n=n, kind=kind, name=name, ok=ok, local=False, ms=ans.ms,
                              tokens=ans.prompt_tokens + ans.completion_tokens, covers=spec["covers"],
                              tab_ok=tab_ok, tab_local=bool(tab and tab.local),
                              tab_tokens=(tab.prompt_tokens + tab.completion_tokens) if tab else 0,
                              text=text, problems=problems))

    # ── Assemble project from the bridge's answers ──
    if only:
        return dict(steps=steps, lint_ok=True, runtime=[])
    shutil.rmtree(OUT_DIR, ignore_errors=True)
    for path, _, tpl in FILES:
        full = os.path.join(OUT_DIR, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(render(split_template(tpl), filled))

    print(f"\n── php -l ({OUT_DIR}) " + "─" * 50)
    lint_ok = True
    for path, _, _ in FILES:
        res = subprocess.run(["php", "-l", os.path.join(OUT_DIR, path)], capture_output=True, text=True)
        good = res.returncode == 0
        lint_ok &= good
        msg = "OK" if good else (res.stdout + res.stderr).strip().splitlines()[0]
        print(f"{'✅' if good else '❌'} {path}: {msg}")

    runtime = []
    if lint_ok:
        res = subprocess.run(["php", "index.php"], cwd=OUT_DIR, capture_output=True, text=True)
        print("\n── Runtime: php index.php " + "─" * 46)
        try:
            report = json.loads(res.stdout.strip().splitlines()[-1])
        except Exception:
            report = {}
            print("❌ cannot parse output:", (res.stdout + res.stderr)[:500])
        runtime = runtime_checks(report)
        for title, good in runtime:
            print(f"{'✅' if good else '❌'} {title}")
        if res.stderr.strip():
            print("STDERR:", res.stderr.strip()[:500])

    return dict(steps=steps, lint_ok=lint_ok, runtime=runtime)


def summarize(runs: list[dict]) -> int:
    print("\n" + "═" * 95)
    print("SUMMARY")
    print("═" * 95)
    failed_total = 0
    for i, r in enumerate(runs, 1):
        steps = r["steps"]
        probes = [s for s in steps if s["kind"] == "probe"]
        slots = [s for s in steps if s["kind"] == "slot"]
        probes_ok = sum(s["ok"] for s in probes)
        probes_local = sum(s["local"] for s in probes)
        slots_ok = sum(s["ok"] for s in slots)
        tabs = [s for s in slots if s["text"]]
        tabs_ok = sum(s["tab_ok"] for s in tabs)
        tabs_local = sum(s["tab_local"] for s in tabs)
        llm_ms = [s["ms"] for s in slots]
        tokens = sum(s["tokens"] for s in steps) + sum(s.get("tab_tokens", 0) for s in slots)
        rt_ok = sum(g for _, g in r["runtime"])
        print(f"Run {i}:")
        print(f"  Probes (must be silent) : {probes_ok}/{len(probes)}  (blocked locally: {probes_local})")
        print(f"  Completion slots        : {slots_ok}/{len(slots)}  (avg LLM {sum(llm_ms) // max(1, len(llm_ms))} ms)")
        print(f"  Silent after Tab        : {tabs_ok}/{len(tabs)}  (blocked locally: {tabs_local})")
        print(f"  php -l                  : {'OK' if r['lint_ok'] else 'FAILED'}")
        print(f"  Runtime assertions      : {rt_ok}/{len(r['runtime'])}" if r["runtime"] else "  Runtime assertions      : skipped")
        print(f"  Gemini tokens spent     : {tokens}")
        failed = [s for s in steps if not s["ok"]]
        for s in failed:
            print(f"   ❌ #{s['n']:02d} {s['name']}: {'; '.join(s.get('problems') or ['not silent'])}")
        for s in tabs:
            if not s["tab_ok"]:
                print(f"   ⚠️ #{s['n']:02d} {s['name']}: keeps writing after Tab")
        failed_total += len(failed) + (0 if r["lint_ok"] else 1) + sum(not g for _, g in r["runtime"])

    covered = sorted({c for r in runs for s in r["steps"] for c in s["covers"]},
                     key=lambda c: (c.split("-")[0], int(re.sub(r"\D", "", c) or 0)))
    print(f"\nCovered cases ({len(covered)}): {', '.join(covered)}")
    return 1 if failed_total else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=int, default=1, help="repeat the whole session N times (flakiness check)")
    ap.add_argument("--verbose", action="store_true", help="print prefix/suffix tails for completion slots")
    ap.add_argument("--only", default="", help="comma-separated slot/probe names to replay (skips assembly)")
    args = ap.parse_args()
    only = {s.strip() for s in args.only.split(",") if s.strip()} or None

    php = subprocess.run(["php", "-v"], capture_output=True, text=True).stdout.splitlines()[:1]
    print("═" * 95)
    print("🚀 LIVE CODING EMULATION: OOP MVC CALCULATOR (PHP) THROUGH zed-gemini-predict")
    print(f"   bridge: {PROXY_URL} | model: {MODEL} | {php[0] if php else 'php: not found'}")
    print("═" * 95)
    try:
        runs = []
        for i in range(args.runs):
            if args.runs > 1:
                print(f"\n################ RUN {i + 1}/{args.runs} ################")
            runs.append(run_once(args.verbose, only))
    except urllib.error.URLError as e:
        print(f"❌ Bridge is not reachable at {PROXY_URL}: {e}")
        return 2
    return summarize(runs)


if __name__ == "__main__":
    sys.exit(main())
