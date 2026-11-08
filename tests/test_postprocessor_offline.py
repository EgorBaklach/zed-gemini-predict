#!/usr/bin/env python3
"""
Offline regression tests for the bridge's deterministic layers (no network, no Gemini tokens).

Every case is a REAL raw Gemini answer captured in /tmp/zed_fim_debug.log during live-coding
emulation (simulate_mvc_live_coding.py) or real Zed sessions, together with the exact cursor
context. They pin down the behaviour of:
  * should_skip_request      - pre-flight Open Semantic Slot gatekeeper
  * clean_completion         - structural post-processor
  * mechanical_paren_closure - fallback when Gemini answers with nothing

Usage (inside WSL):  python3 tests/test_postprocessor_offline.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import zed_fim_proxy as bridge  # noqa: E402

# (title, prefix, suffix, raw Gemini answer, expected text sent to Zed)
CLEAN_CASES = [
    ("Fluent chain: lone `)` must survive (was eaten by prefix-repetition check)",
     "$divide = (new RequestBuilder())->withA(20)->withB(4)->withOp(Operation::Divide",
     "\n    ->build();\n", ")", ")"),
    ("Fluent chain: invented `->withPath()` is cut",
     "$divide = (new RequestBuilder())->withA(20)->withB(4)->withOp(Operation::Divide",
     "\n    ->build();\n", ")->withPath('/calculate')", ")"),
    ("Fluent chain: operator debris `)>` is cut",
     "$divide = (new RequestBuilder())->withA(20)->withB(4)->withOp(Operation::Divide",
     "\n    ->build();\n", ")>", ")"),
    ("Nested call before same-line `, $result);`: inner sprintf( gets closed",
     "        $this->remember(sprintf('%s %s %s = %s', $a, $op->value, $b, ",
     ", $result);\n\n        return $result;", "$result", "$result)"),
    ("Argument echo `$b, |` -> `$b` is rejected (silence beats wrong code)",
     "        $this->remember(sprintf('%s %s %s = %s', $a, $op->value, $b, ",
     ", $result);\n\n        return $result;", "$b", ""),
    ("Parens inside string literals are ignored by the balancer",
     "        $msg = sprintf('User #%d (%s) from %s', $id, $name, ",
     "\n        return $msg;", "$ip);", "$ip);"),
    ("Tab before `));`: pure suffix duplicate is dropped",
     "        return array_values(array_filter($this->results, fn(float $r): bool => $r > 0.0",
     "));\n    }", "));", ""),
    ("Tab after match arm: `;` is invalid inside match",
     "            self::Modulo => 'Остаток от деления'",
     "\n        };\n    }", ";", ""),
    ("Tab after last match arm: `};` already exists on the next line",
     "            self::Modulo => 'Остаток от деления'",
     "\n        };\n    }", "};", ""),
    ("match default arm: trailing `;` is a syntax error inside match",
     "            default => ",
     "\n        };\n    }", "'Unknown';", "'Unknown'"),
    ("Array item before another item: trailing `;` is stripped",
     "            'result' => ",
     "\n            'error' => $error,\n        ];", "$result;", "$result"),
    ("Arrow fn argument in a statement keeps its `);`",
     "        array_map(fn($x) => ",
     "\n        return $list;", "$x * 2, $list);", "$x * 2, $list);"),
    ("Tab before existing `, $this->results);`: extra `);` is dropped",
     "        return array_map(fn(float $r): float => round($r, $precision)",
     ", $this->results);\n    }", ");", ""),
    ("try { + `} catch` on the same line is moved to a new line",
     "<?php\ntry {", "\n", "} catch (\\Throwable $e) {\n    throw $e;\n}",
     "\n} catch (\\Throwable $e) {\n    throw $e;\n}"),
    ("Token debris `)</table>` is cut",
     "$divide = (new RequestBuilder())->withA(20)->withB(4)->withOp(Operation::Divide",
     "\n    ->build();\n", ")</table>", ")"),
    ("Declaration header debris `?): array;` is rejected",
     "    public function getHistory(", "\n}\n", "?): array;", ""),
    ("Declaration header debris `)?: array;` is rejected",
     "    public function getHistory(", "\n}\n", ")?: array;", ""),
    ("Valid header with params and union type is kept",
     "    public function save(array $data", "\n}\n", ", ?int $id = null): int|false;", ", ?int $id = null): int|false;"),
    ("Valid header return type `: ?\\DateTimeImmutable` is kept",
     "    public function getCreatedAt(", "\n    {", "): ?\\DateTimeImmutable", "): ?\\DateTimeImmutable"),
    ("`<` comparison inside code is not mistaken for a tag",
     "        for ($i = 1; $i ", "\n        }", "< $count; $i++) {", "< $count; $i++) {"),
    ("Tab after match arm: invented `Operation::Power` case is cut, trailing comma kept",
     "            Operation::Modulo => $a % $b",
     "\n        };", ",\n            Operation::Power => $a ** $b", ","),
    ("Class header: implements only, never the class body",
     "final class StripeGateway implements ",
     "\n}", "PaymentGatewayInterface {\n    public function charge(int $amount): bool\n    {\n        return true;\n    }",
     "PaymentGatewayInterface {"),
    ("Method header: return type only, never the body",
     "    public function getHistory(",
     "\n    {\n        return $this->history;\n    }", "): array\n    {\n        return [];", "): array"),
    ("try { skeleton: body is moved to a new line",
     "    public function safeHistory(): string\n    {\n        try {",
     "\n    }\n", "            return $this->history();\n        } catch (\\Throwable) {\n            return '';\n        }",
     "\n            return $this->history();\n        } catch (\\Throwable) {\n            return '';\n        }"),
    ("Enum case gets its `;`",
     "    case Divide = ", "\n    case Modulo = '%';", "'/'", "'/';"),
    ("Leaked `<?php` tag is stripped",
     "    case Divide = ", "\n}\n", "'/'<?php", "'/';"),
    ("Closure refactor: `=> expr` after `use (` becomes `{ return expr; }`",
     "        return array_filter($this->results, function (float $r) use (",
     ");", "$min) => $r >= $min", "$min) {\n            return $r >= $min;\n        }"),
    ("Nested if: invented `&& ...` clause is stripped",
     "        if ($op === Operation::Divide && $b === 0.0",
     "\n            throw new \\DivisionByZeroError('x');", ") && $a > 0) {", ") {"),
]

# (title, prefix, suffix, expected skip?)
SKIP_CASES = [
    ("for header with `;` inside open parens is NOT a finished statement",
     "        for ($i = 1; $i <= $count; ", "\n            $rows[] = $i;\n        }", False),
    ("Finished statement `...;` is skipped", "        $x = foo($a);", "\n", True),
    ("Finished array item `'k' => $v,` is skipped", "            'error' => $error,", "\n        ];", True),
    ("Block header `if (...) {` is skipped", "        if ($ok) {", "\n        }", True),
    ("`try {` is NOT skipped (catch skeleton allowed)", "        try {", "\n    }", False),
    ("Closure closed before `);` is skipped",
     "        return array_filter($r, function ($x) use ($m) { return $x >= $m; }", ");", True),
    ("Mid-identifier `$this->mod|el` is skipped", "        $this->mod", "el", True),
    ("Bare `$x = [` is skipped", "        $payload = [", "];", True),
    ("Bare quote inside array is skipped", "            '", "'", True),
    ("Constructor promotion `private readonly ` is NOT skipped", "        private readonly ", "\n    ) {}", False),
    ("`implements ` is NOT skipped", "final class CalculatorModel implements ", "\n{", False),
]

# (title, prefix, suffix, expected mechanical closure)
FALLBACK_CASES = [
    ("Concatenation before ` . '.php';`",
     "    $file = rtrim(__DIR__, '/') . '/src/' . ltrim($relative", " . '.php';\n", ")"),
    ("Fluent chain continues with `->build();` on the next line",
     "$d = (new B())->withOp(Operation::Divide", "\n    ->build();", ")"),
    ("Cursor after `, ` is an argument slot -> no mechanical guess",
     "        $x = sprintf('%s', ", ");", ""),
    ("End of line without continuation -> no guess (could be `;` or ` {`)",
     "        $x = foo($a", "\n        return $x;", ""),
]


def main() -> int:
    failed = 0
    print("── clean_completion ──")
    for title, prefix, suffix, raw, expected in CLEAN_CASES:
        got = bridge.clean_completion(raw, prefix, suffix)
        ok = got == expected
        failed += not ok
        print(f"{'✅' if ok else '❌'} {title}" + ("" if ok else f"\n     expected {expected!r}\n     got      {got!r}"))

    print("── should_skip_request ──")
    for title, prefix, suffix, expected in SKIP_CASES:
        got = bridge.should_skip_request(prefix, suffix)
        ok = got == expected
        failed += not ok
        print(f"{'✅' if ok else '❌'} {title}" + ("" if ok else f" (expected {expected}, got {got})"))

    print("── mechanical_paren_closure ──")
    for title, prefix, suffix, expected in FALLBACK_CASES:
        got = bridge.mechanical_paren_closure(prefix, suffix)
        ok = got == expected
        failed += not ok
        print(f"{'✅' if ok else '❌'} {title}" + ("" if ok else f" (expected {expected!r}, got {got!r})"))

    total = len(CLEAN_CASES) + len(SKIP_CASES) + len(FALLBACK_CASES)
    print(f"\n{total - failed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
