#!/usr/bin/env python3
"""
Эмулятор живого кодирования ООП MVC Калькулятора на PHP 8.3 в редакторе Zed.
Симулирует работу разработчика шаг за шагом:
1. Ввод кода в буфер (Model -> View -> Controller) + реальные ловушки курсора из Zed.
2. Срабатывание автодополнения на промежуточных фазах набора (Open Slots vs Syntactic Closure).
3. Нажатие Tab (принятие подсказки в буфер) и мгновенный повторный запрос от Zed с новой позиции курсора!
4. Сборка итогового ООП MVC Калькулятора из полученных ответов моста, проверка через `php -l` и реальный запуск расчётов.
"""
import json
import subprocess
import time
import urllib.request

PROXY_URL = "http://127.0.0.1:8089/v1/completions"


def query_proxy(prefix: str, suffix: str) -> tuple[str, int, int]:
    prompt = f"<|fim_prefix|>{prefix}<|fim_suffix|>{suffix}<|fim_middle|>"
    body = json.dumps(
        {
            "model": "gemini-3.5-flash-lite",
            "prompt": prompt,
            "max_tokens": 80,
            "stop": ["<|endoftext|>"],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        PROXY_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    dt = int((time.time() - t0) * 1000)
    text = data["choices"][0]["text"]
    comp_tokens = data.get("usage", {}).get("completion_tokens", 0)
    return text, dt, comp_tokens


mvc_live_steps = [
    # =========================================================================
    # ЧАСТЬ 1: Model — Operation Enum & CalculatorModel
    # =========================================================================
    {
        "key": "enum_divide",
        "stage": "1. [Enum] Backed Enum операций: остановились после case Divide = ",
        "mode": "complete",
        "prefix": (
            "<?php\ndeclare(strict_types=1);\n\nnamespace App\\Models;\n\n"
            "enum Operation: string\n{\n"
            "    case Add = '+';\n"
            "    case Subtract = '-';\n"
            "    case Multiply = '*';\n"
            "    case Divide = "
        ),
        "suffix": "\n}\n",
    },
    {
        "key": "slot_blank",
        "stage": "2. [Model] Открыли класс модели, курсор на пустой строке внутри класса",
        "mode": "open_slot",
        "prefix": (
            "<?php\ndeclare(strict_types=1);\n\nnamespace App\\Models;\n\n"
            "final class CalculatorModel\n{\n    "
        ),
        "suffix": "\n}\n",
    },
    {
        "key": "slot_pub_fn",
        "stage": "3. [Model] Начали объявлять метод: public function ",
        "mode": "open_slot",
        "prefix": (
            "<?php\ndeclare(strict_types=1);\n\nnamespace App\\Models;\n\n"
            "final class CalculatorModel\n{\n"
            "    public function "
        ),
        "suffix": "\n}\n",
    },
    {
        "key": "slot_bare_if",
        "stage": "4. [Model] Внутри calculate() написали голый if ( — думаем над проверкой деления на 0",
        "mode": "open_slot",
        "prefix": (
            "<?php\ndeclare(strict_types=1);\n\nnamespace App\\Models;\n\n"
            "final class CalculatorModel\n{\n"
            "    public function calculate(float $a, float $b, Operation $op): float\n    {\n"
            "        if ("
        ),
        "suffix": "\n    }\n}\n",
    },
    {
        "key": "model_if_div_zero",
        "stage": "5. [Model] Написали условие деления на ноль без закрытия скобки: if ($op === Operation::Divide && $b === 0.0",
        "mode": "complete",
        "prefix": (
            "<?php\ndeclare(strict_types=1);\n\nnamespace App\\Models;\n\n"
            "final class CalculatorModel\n{\n"
            "    public function calculate(float $a, float $b, Operation $op): float\n    {\n"
            "        if ($op === Operation::Divide && $b === 0.0"
        ),
        "suffix": "\n            throw new \\DivisionByZeroError('Division by zero');\n        }\n    }\n}\n",
    },
    {
        "key": "slot_bare_match",
        "stage": "6. [Model] Начали писать return match ( без аргумента",
        "mode": "open_slot",
        "prefix": (
            "<?php\ndeclare(strict_types=1);\n\nnamespace App\\Models;\n\n"
            "final class CalculatorModel\n{\n"
            "    public function calculate(float $a, float $b, Operation $op): float\n    {\n"
            "        return match ("
        ),
        "suffix": "\n    }\n}\n",
    },
    {
        "key": "model_match_div",
        "stage": "7. [Model] Заполнили ветки match ($op), остановились на Operation::Divide => ",
        "mode": "complete",
        "prefix": (
            "<?php\ndeclare(strict_types=1);\n\nnamespace App\\Models;\n\n"
            "final class CalculatorModel\n{\n"
            "    public function calculate(float $a, float $b, Operation $op): float\n    {\n"
            "        if ($op === Operation::Divide && $b === 0.0) {\n"
            "            throw new \\DivisionByZeroError('Division by zero');\n"
            "        }\n"
            "        return match ($op) {\n"
            "            Operation::Add => $a + $b,\n"
            "            Operation::Subtract => $a - $b,\n"
            "            Operation::Multiply => $a * $b,\n"
            "            Operation::Divide => "
        ),
        "suffix": "\n        };\n    }\n}\n",
    },
    {
        "key": "model_refactor_closure",
        "stage": "8. [Model] Рефакторинг фильтрации истории: переводим fn() => в function () use ($minResult)",
        "mode": "complete",
        "prefix": (
            "<?php\ndeclare(strict_types=1);\n\nnamespace App\\Models;\n\n"
            "final class CalculatorModel\n{\n"
            "    public function filterHistory(array $history, float $minResult): array\n    {\n"
            "        // return array_filter($history, fn(array $item) => $item['result'] >= $minResult);\n"
            "        return array_filter($history, function (array $item) use ("
        ),
        "suffix": ");\n    }\n}\n",
    },

    # =========================================================================
    # ЧАСТЬ 2: View — CalculatorView + Реальные ловушки Zed из логов
    # =========================================================================
    {
        "key": "slot_bare_var_dollar",
        "stage": "9. [View / Ловушка Zed] Начали вводить переменную `$` (или `$va` в середине слова)",
        "mode": "open_slot",
        "prefix": (
            "<?php\ndeclare(strict_types=1);\n\nnamespace App\\Views;\n\n"
            "final class CalculatorView\n{\n"
            "    public function renderText(float $a, string $op, float $b, float $result): string\n    {\n"
            "        $"
        ),
        "suffix": "formatted\n    }\n}\n",
    },
    {
        "key": "slot_empty_array",
        "stage": "10. [View / Ловушка Zed] Открыли пустой массив `$payload = [` (Zed авто-закрыл `]`)",
        "mode": "open_slot",
        "prefix": (
            "<?php\ndeclare(strict_types=1);\n\nnamespace App\\Views;\n\n"
            "final class CalculatorView\n{\n"
            "    public function renderJson(bool $success, ?float $result, ?string $error = null): string\n    {\n"
            "        $payload = ["
        ),
        "suffix": "];\n    }\n}\n",
    },
    {
        "key": "slot_bare_quote_in_array",
        "stage": "11. [View / Ловушка Zed] Внутри массива поставили пустую кавычку `'` для нового ключа",
        "mode": "open_slot",
        "prefix": (
            "<?php\ndeclare(strict_types=1);\n\nnamespace App\\Views;\n\n"
            "final class CalculatorView\n{\n"
            "    public function renderJson(bool $success, ?float $result, ?string $error = null): string\n    {\n"
            "        $payload = [\n"
            "            '"
        ),
        "suffix": "'\n        ];\n    }\n}\n",
    },
    {
        "key": "view_sprintf",
        "stage": "12. [View] Закрываем аргументы sprintf('%.2f %s %.2f = %.2f', $a, $op, $b, ",
        "mode": "complete",
        "prefix": (
            "<?php\ndeclare(strict_types=1);\n\nnamespace App\\Views;\n\n"
            "final class CalculatorView\n{\n"
            "    public function renderText(float $a, string $op, float $b, float $result): string\n    {\n"
            "        $formatted = sprintf('%.2f %s %.2f = %.2f', $a, $op, $b, "
        ),
        "suffix": "\n        return $formatted;\n    }\n}\n",
    },
    {
        "key": "view_array_item",
        "stage": "13. [View] Формируем ассоциативный массив ответа для JSON перед ];",
        "mode": "complete",
        "prefix": (
            "<?php\ndeclare(strict_types=1);\n\nnamespace App\\Views;\n\n"
            "final class CalculatorView\n{\n"
            "    public function renderJson(bool $success, ?float $result, ?string $error = null): string\n    {\n"
            "        $payload = [\n"
            "            'success' => $success,\n"
            "            'result' => $result,\n"
            "            'error' => "
        ),
        "suffix": "\n        ];\n        return json_encode($payload, JSON_THROW_ON_ERROR);\n    }\n}\n",
    },

    # =========================================================================
    # ЧАСТЬ 3: Controller — CalculatorController
    # =========================================================================
    {
        "key": "ctrl_ctor",
        "stage": "14. [Controller] Constructor Property Promotion (PHP 8.2 readonly): инжектим CalculatorView",
        "mode": "complete",
        "prefix": (
            "<?php\ndeclare(strict_types=1);\n\nnamespace App\\Controllers;\n\n"
            "use App\\Models\\CalculatorModel;\n"
            "use App\\Models\\Operation;\n"
            "use App\\Views\\CalculatorView;\n\n"
            "final readonly class CalculatorController\n{\n"
            "    public function __construct(\n"
            "        private CalculatorModel $model,\n"
            "        private "
        ),
        "suffix": "\n    ) {}\n}\n",
    },
    {
        "key": "slot_mid_keyword",
        "stage": "15. [Controller / Ловушка Zed] Печатаем ключевое слово по буквам `fo` или курсор внутри `t|ry`",
        "mode": "open_slot",
        "prefix": (
            "<?php\ndeclare(strict_types=1);\n\nnamespace App\\Controllers;\n\n"
            "final readonly class CalculatorController\n{\n"
            "    public function handle(array $request): string\n    {\n"
            "        fo"
        ),
        "suffix": "\n    }\n}\n",
    },
    {
        "key": "slot_member_op",
        "stage": "16. [Controller] Обращение к свойству $this->model-> (ждём LSP, мост должен молчать)",
        "mode": "open_slot",
        "prefix": (
            "<?php\ndeclare(strict_types=1);\n\nnamespace App\\Controllers;\n\n"
            "final readonly class CalculatorController\n{\n"
            "    public function handle(array $request): string\n    {\n"
            "        $res = $this->model->"
        ),
        "suffix": "\n    }\n}\n",
    },
    {
        "key": "ctrl_if_validate",
        "stage": "17. [Controller] Вложенные скобки валидации входных параметров if (!isset($request['a']) || !is_numeric($request['b']",
        "mode": "complete",
        "prefix": (
            "<?php\ndeclare(strict_types=1);\n\nnamespace App\\Controllers;\n\n"
            "final readonly class CalculatorController\n{\n"
            "    public function handle(array $request): string\n    {\n"
            "        if (!isset($request['a']) || !is_numeric($request['b']"
        ),
        "suffix": "\n            return $this->view->renderJson(false, null, 'Invalid input');\n        }\n    }\n}\n",
    },
    {
        "key": "ctrl_catch",
        "stage": "18. [Controller] Написали тело try и остановились на } catch (",
        "mode": "complete",
        "prefix": (
            "<?php\ndeclare(strict_types=1);\n\nnamespace App\\Controllers;\n\n"
            "final readonly class CalculatorController\n{\n"
            "    public function handle(array $request): string\n    {\n"
            "        try {\n"
            "            $op = Operation::from((string) $request['op']);\n"
            "            $result = $this->model->calculate((float) $request['a'], (float) $request['b'], $op);\n"
            "            return $this->view->renderJson(true, $result);\n"
            "        } catch ("
        ),
        "suffix": "\n            return $this->view->renderJson(false, null, $e->getMessage());\n        }\n    }\n}\n",
    },
]

print("=" * 95)
print("🚀 ЭМУЛЯЦИЯ ЖИВОГО КОДИРОВАНИЯ ООП MVC КАЛЬКУЛЯТОРА В ZED (PHP 8.3)")
print("=" * 95)

results = {}
post_tab_issues = []
passed = 0

for step in mvc_live_steps:
    text, dt, tok = query_proxy(step["prefix"], step["suffix"])
    results[step["key"]] = text
    mode = step["mode"]

    if mode == "open_slot":
        ok = text == ""
        if ok:
            passed += 1
        status = "✅ МОЛЧИТ (0 токенов)" if ok else "❌ ГАЛЛЮЦИНАЦИЯ!"
        print(f"\n{step['stage']}")
        print(f"   Режим: Открытый слот | Статус: {status} | {dt} мс | Ответ: {text!r}")
    else:
        ok = text != ""
        if ok:
            passed += 1
        status = "✅ ДОПИСАЛ СИНТАКСИС" if ok else "❌ ПРОМОЛЧАЛ!"
        print(f"\n{step['stage']}")
        print(f"   Режим: Alt+\\ Замыкание | Статус: {status} | {dt} мс (+{tok} tok)")
        print(f"   >>> Подсказка моста: {text!r}")

        if text:
            new_prefix = step["prefix"] + text
            follow_text, follow_dt, follow_tok = query_proxy(new_prefix, step["suffix"])
            new_current_line = new_prefix.rsplit("\n", 1)[-1]
            if follow_text == "":
                print(f"   [После нажатия Tab] Курсор в конце `{new_current_line.strip()}` -> ✅ МОЛЧИТ ({follow_dt} мс)")
            else:
                print(f"   [После нажатия Tab] Курсор в конце `{new_current_line.strip()}` -> ⚠️ ПРОДОЛЖИЛ ({follow_dt} мс): {follow_text!r}")
                post_tab_issues.append((step["stage"], new_current_line, follow_text))

print("\n" + "=" * 95)
print(f"ИТОГ СИМУЛЯЦИИ ШАГОВ: {passed}/{len(mvc_live_steps)} успешно | Пост-Tab авто-продолжений: {len(post_tab_issues)}")
print("=" * 95)

# Собираем реальный исполняемый PHP-файл MVC Калькулятора с подставленными ответами моста!
assembled_php = f"""<?php
declare(strict_types=1);

namespace App\\Models {{
    enum Operation: string
    {{
        case Add = '+';
        case Subtract = '-';
        case Multiply = '*';
        case Divide = {results['enum_divide']}
    }}

    final class CalculatorModel
    {{
        public function calculate(float $a, float $b, Operation $op): float
        {{
            if ($op === Operation::Divide && $b === 0.0{results['model_if_div_zero']}
                throw new \\DivisionByZeroError('Division by zero');
            }}
            return match ($op) {{
                Operation::Add => $a + $b,
                Operation::Subtract => $a - $b,
                Operation::Multiply => $a * $b,
                Operation::Divide => {results['model_match_div']}
            }};
        }}

        public function filterHistory(array $history, float $minResult): array
        {{
            return array_filter($history, function (array $item) use ({results['model_refactor_closure']});
        }}
    }}
}}

namespace App\\Views {{
    final class CalculatorView
    {{
        public function renderText(float $a, string $op, float $b, float $result): string
        {{
            $formatted = sprintf('%.2f %s %.2f = %.2f', $a, $op, $b, {results['view_sprintf']}
            return $formatted;
        }}

        public function renderJson(bool $success, ?float $result, ?string $error = null): string
        {{
            $payload = [
                'success' => $success,
                'result' => $result,
                'error' => {results['view_array_item']}
            ];
            return json_encode($payload, JSON_THROW_ON_ERROR);
        }}
    }}
}}

namespace App\\Controllers {{
    use App\\Models\\CalculatorModel;
    use App\\Models\\Operation;
    use App\\Views\\CalculatorView;

    final readonly class CalculatorController
    {{
        public function __construct(
            private CalculatorModel $model,
            private {results['ctrl_ctor']}
        ) {{}}

        public function handle(array $request): string
        {{
            if (!isset($request['a']) || !is_numeric($request['b']{results['ctrl_if_validate']}
                return $this->view->renderJson(false, null, 'Invalid input');
            }}

            try {{
                $op = Operation::from((string) $request['op']);
                $result = $this->model->calculate((float) $request['a'], (float) $request['b'], $op);
                return $this->view->renderJson(true, $result);
            }} catch ({results['ctrl_catch']}
                return $this->view->renderJson(false, null, $e->getMessage());
            }}
        }}
    }}
}}

namespace {{
    use App\\Controllers\\CalculatorController;
    use App\\Models\\CalculatorModel;
    use App\\Views\\CalculatorView;

    $model = new CalculatorModel();
    $view = new CalculatorView();
    $controller = new CalculatorController($model, $view);

    echo "1) 10 + 5   => " . $controller->handle(['a' => 10, 'b' => 5, 'op' => '+']) . PHP_EOL;
    echo "2) 20 / 4   => " . $controller->handle(['a' => 20, 'b' => 4, 'op' => '/']) . PHP_EOL;
    echo "3) 10 / 0   => " . $controller->handle(['a' => 10, 'b' => 0, 'op' => '/']) . PHP_EOL;
    echo "4) TextView => " . $view->renderText(7, '*', 6, 42) . PHP_EOL;
    $filtered = $model->filterHistory([['result' => 5.0], ['result' => 42.0]], 10.0);
    echo "5) History  => count=" . count($filtered) . PHP_EOL;
}}
"""

demo_path = "/tmp/mvc_calculator_demo.php"
with open(demo_path, "w", encoding="utf-8") as f:
    f.write(assembled_php)

print("\n🔍 ПРОВЕРКА СГЕНЕРИРОВАННОГО MVC КАЛЬКУЛЯТОРА ЧЕРЕЗ `php -l` И ЗАПУСК:")
lint = subprocess.run(["php", "-l", demo_path], capture_output=True, text=True)
print("   [php -l]:", lint.stdout.strip() or lint.stderr.strip())
if lint.returncode == 0:
    run = subprocess.run(["php", demo_path], capture_output=True, text=True)
    print("   [Вывод работы MVC-калькулятора]:")
    for line in run.stdout.strip().splitlines():
        print("     ", line)
    if run.stderr:
        print("   [STDERR]:", run.stderr)
