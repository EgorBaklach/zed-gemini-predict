#!/usr/bin/env python3
"""
Offline regression tests for the bridge's deterministic layers (no network, no Gemini tokens).

Every case is a REAL raw Gemini answer captured in /tmp/zed_fim_debug.log during live-coding
emulation (simulate_mvc_live_coding.py) or real Zed sessions, together with the exact cursor
context. They pin down the behaviour of the PHP profile:
  * PROFILE.should_skip  - pre-flight Open Semantic Slot gatekeeper
  * postprocess()        - ordered post-processing rules (+ which rule fired)
  * PROFILE.fallback     - mechanical paren closure when Gemini answers with nothing

Usage (inside WSL):  python3 tests/test_postprocessor_offline.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from bridge.php import PROFILE  # noqa: E402
from bridge.pipeline import postprocess  # noqa: E402

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
    ("Tab after match arm: `;')` debris is dropped",
     "            self::Modulo => 'Остаток от деления'", "\n        };\n    }", ";');", ""),
    ("Tab after match arm: `</i>;` debris is dropped",
     "            self::Modulo => 'Остаток от деления'", "\n        };\n    }", "</i>;", ""),
    ("try { skeleton: invented statement after the closed catch block is cut",
     "    public function safeHistory(): string\n    {\n        try {", "\n    }\n",
     "\n        } catch (\\Throwable $e) {\n            return '';\n        }\n        return $this->",
     "\n        } catch (\\Throwable $e) {\n            return '';\n        }"),
    ("try { skeleton with body: `} catch {` line keeps the block open",
     "<?php\ntry {", "\n",
     "\n    $db->exec($sql);\n} catch (\\Throwable $e) {\n    throw $e;\n}",
     "\n    $db->exec($sql);\n} catch (\\Throwable $e) {\n    throw $e;\n}"),
    ("Argument echo: base of an earlier argument (`$op` of `$op->value`) is rejected",
     "        $this->remember(sprintf('%s %s %s = %s', $a, $op->value, $b, ",
     ", $result);\n\n        return $result;", "$op", ""),
    ("Argument echo check ignores commas/parens inside the format string",
     "        $msg = sprintf('a, (b), %s, %s', $name, ", ");", "$ip", "$ip"),
    ("Dangling `[` after a finished string literal is debris (`'/'[`)",
     "    case Divide = ", "\n    case Modulo = '%';", "'/'[", "'/';"),
    ("A `[` inside a string literal is kept",
     "        $s = ", "\n", "'a['", "'a['"),
    ("Constructor promotion: invented second dependency is cut",
     "    public function __construct(\n        private readonly LoggerInterface $logger,\n        private readonly ",
     "\n    ) {}\n}",
     "PaymentGatewayInterface $paymentGateway,\n        private readonly OrderRepositoryInterface $repository",
     "PaymentGatewayInterface $paymentGateway,"),
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


# (title, prefix, suffix, raw Gemini answer, rule that must be reported in the debug log)
RULE_TRACE_CASES = [
    ("Invented fluent call is attributed to guard_fluent_chain",
     "$d = (new B())->withOp(Operation::Divide", "\n    ->build();", ")->withPath('/x')", "guard_fluent_chain"),
    ("Argument echo is attributed to reject_argument_echo",
     "        $s = sprintf('%s %s', $a, $b, ", ", $c);", "$b", "reject_argument_echo"),
    ("Inner call closed before same-line suffix is attributed to balance_parens",
     "        $this->remember(sprintf('%s', $a, ", ", $result);", "$result", "balance_parens"),
    ("Empty Gemini answer + continuation is attributed to the fallback",
     "    $file = ltrim($relative", " . '.php';", "", "fallback:mechanical_paren_closure"),
]


# (title, prefix, suffix, expected local completion) - deterministic answers without Gemini
_METHOD = "    public function check(): string\n    {\n"
LOCAL_CASES = [
    ("Allman block, body done, next statement back at `{` level -> close with `}` on a new line",
     _METHOD + "        if(!$this->dispatcher->dispatch())\n        {\n            return json_encode(['status' => 'error']);",
     "\n\n        return json_encode(['status' => 'ok']);\n    }\n}\n",
     "\n        }"),
    ("K&R `if (...) {` block, last statement of the method -> close before the method's `}`",
     _METHOD + "        if ($x) {\n            return 1;", "\n    }\n}\n", "\n        }"),
    ("Blank line already at the `{` indentation -> `}`",
     _METHOD + "        if ($x)\n        {\n            return 1;\n        ", "\n        return 2;\n    }\n", "}"),
    ("Blank line still at body indentation -> silent (insertion cannot dedent)",
     _METHOD + "        if ($x)\n        {\n            return 1;\n            ", "\n        return 2;\n    }\n", ""),
    ("Block already closed below -> silent",
     _METHOD + "        if ($x)\n        {\n            return 1;", "\n        }\n        return 2;\n    }\n", ""),
    ("`} else {` below closes the block -> silent",
     _METHOD + "        if ($x) {\n            $a = 1;", "\n        } else {\n            $a = 2;\n        }\n", ""),
    ("Body continues below (deeper indent) -> silent",
     _METHOD + "        if ($x)\n        {\n            $a = 1;", "\n            $b = 2;\n        }\n", ""),
    ("Empty block (no body yet) -> silent (open slot)",
     _METHOD + "        if ($x)\n        {", "\n        return 2;\n    }\n", ""),
    ("Cursor before the body (after Tab) -> silent (FIM inserts only at the cursor)",
     _METHOD + "        if ($x)\n        {\n            ", "return 1;\n        return 2;\n    }\n", ""),
    ("Unfinished statement on the cursor line -> silent",
     _METHOD + "        if ($x)\n        {\n            $a = foo(", "\n        return 2;\n    }\n", ""),
    ("Normal statement inside a well-formed method -> silent",
     _METHOD + "        $a = 1;", "\n        $b = 2;\n    }\n", ""),
    ("Braces inside strings are ignored",
     _METHOD + "        if ($x)\n        {\n            $s = '{ not a block';", "\n        return $s;\n    }\n", "\n        }"),
]


def main() -> int:
    failed = 0
    print("── local completion (PROFILE.local_completion) ──")
    for title, prefix, suffix, expected in LOCAL_CASES:
        got = PROFILE.local_completion(prefix, suffix)
        ok = got == expected
        failed += not ok
        print(f"{'✅' if ok else '❌'} {title}" + ("" if ok else f" (expected {expected!r}, got {got!r})"))

    print("── postprocess (what Zed receives) ──")
    for title, prefix, suffix, raw, expected in CLEAN_CASES:
        got, _ = postprocess(raw, prefix, suffix, PROFILE)
        ok = got == expected
        failed += not ok
        print(f"{'✅' if ok else '❌'} {title}" + ("" if ok else f"\n     expected {expected!r}\n     got      {got!r}"))

    print("── rule trace (debug log `rules`) ──")
    for title, prefix, suffix, raw, rule in RULE_TRACE_CASES:
        _, applied = postprocess(raw, prefix, suffix, PROFILE)
        ok = rule in applied
        failed += not ok
        print(f"{'✅' if ok else '❌'} {title}" + ("" if ok else f" (got {applied})"))

    print("── gatekeeper (PROFILE.should_skip) ──")
    for title, prefix, suffix, expected in SKIP_CASES:
        got = PROFILE.should_skip(prefix, suffix)
        ok = got == expected
        failed += not ok
        print(f"{'✅' if ok else '❌'} {title}" + ("" if ok else f" (expected {expected}, got {got})"))

    print("── fallback (PROFILE.fallback) ──")
    for title, prefix, suffix, expected in FALLBACK_CASES:
        got = PROFILE.fallback(prefix, suffix)
        ok = got == expected
        failed += not ok
        print(f"{'✅' if ok else '❌'} {title}" + ("" if ok else f" (expected {expected!r}, got {got!r})"))

    total = len(LOCAL_CASES) + len(CLEAN_CASES) + len(RULE_TRACE_CASES) + len(SKIP_CASES) + len(FALLBACK_CASES)
    print(f"\n{total - failed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
