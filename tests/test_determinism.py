import json
import time
import urllib.request

open_slot_tests = [
    ("1. Пустая строка с отступом", "<?php\n        ", "\nreturn $x;"),
    ("2. Одиночная открывающая скобка {", "<?php\nif ($ok)\n        {", "\n}"),
    ("3. Голый if(", "<?php\n        if(", ")\nreturn $x;"),
    ("4. Голый elseif (", "<?php\n} elseif (", ") {\n}"),
    ("5. Голый while (", "<?php\nwhile (", ") {\n}"),
    ("6. Голый foreach (", "<?php\nforeach (", ") {\n}"),
    ("7. Голый match (", "<?php\n$v = match (", ") {\n};"),
    ("8. Голое присваивание $res = ", "<?php\n        $res = ", "\nreturn $res;"),
    ("9. Присваивание свойству $this->cache = ", "<?php\n        $this->cache = ", "\n"),
    ("10. Присваивание в массив $data['key'] ??= ", "<?php\n        $data['key'] ??= ", "\n"),
    ("11. Оператор new без класса: $svc = new ", "<?php\n        $svc = new ", "\n"),
    ("12. Оператор объекта $this-> (ждем LSP)", "<?php\n        $this->", "\n"),
    ("13. Nullsafe оператор $user?->profile?->", "<?php\n        $name = $user?->profile?->", "\n"),
    ("14. Статический оператор self::", "<?php\n        return self::", "\n"),
    ("15. Голый return / throw new ", "<?php\n        throw new ", "\n}"),
    ("16. Голый public function / комментарий //", "<?php\nclass A {\n    public function ", "\n}"),
]

deterministic_tests = [
    ("17. Блок catch ( — должен работать!", "<?php\ntry {\n    $db->exec($sql);\n} catch (", "\n    throw $e;\n}"),
    ("18. Голый try { — каркас catch", "<?php\ntry {", "\n"),
    ("19. Enum case Cancelled = — должен работать!", "<?php\nenum Status: string {\n    case Active = 'active';\n    case Cancelled = ", "\n}"),
    ("20. Начатый массив $a = ['id' => $id, 'ok' => ", "<?php\n$a = [\n    'id' => $id,\n    'ok' => ", "\n];"),
    ("21. Вложенное условие if (isset() && !empty(", "<?php\nif ($request->getMethod() === 'POST' && !empty($body", "\n    return true;\n}"),
    ("22. Цепочка функций rtrim() . ltrim(", "<?php\n$path = rtrim($dir, '/') . '/' . ltrim($file", "\nreturn $path;"),
    ("23. Рефакторинг fn() => в function() use ()", "<?php\n$rate = 1.2;\n// array_map(fn($x) => $x * $rate, $list);\n$res = array_map(function ($x) use (", ", $list);"),
    ("24. Обратный рефакторинг в fn() =>", "<?php\n$p = 'id_';\n// array_map(function ($r) use ($p) { return $p . $r['id']; }, $rows);\n$ids = array_map(fn($r) => ", ", $rows);"),
    ("25. Вывод типа геттера в Trait", "<?php\ntrait T {\n    private ?\\DateTimeImmutable $createdAt = null;\n    public function getCreatedAt(", "\n    {\n        return $this->createdAt;\n    }\n}"),
    ("26. Встроенная функция json_decode с флагом", "<?php\n$data = json_decode($rawJson, true, 512, ", "\n"),
]

print("=== ЧАСТЬ 1: ОТКРЫТЫЕ СМЫСЛОВЫЕ СЛОТЫ (должны вернуть '' за ~2 мс) ===")
for label, prefix, suffix in open_slot_tests:
    prompt = f"<|fim_prefix|>{prefix}<|fim_suffix|>{suffix}<|fim_middle|>"
    body = json.dumps({"model": "gemini-3.5-flash-lite", "prompt": prompt, "max_tokens": 80}).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:8089/v1/completions", data=body, headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    dt = int((time.monotonic() - t0) * 1000)
    text = data["choices"][0]["text"]
    status = "OK" if text == "" else "FAIL"
    print(f"[{status} | {dt:3d} ms] {label:46s} -> {text!r}")

print("\n=== ЧАСТЬ 2: ДЕТЕРМИНИРОВАННЫЕ СИНТАКСИЧЕСКИЕ КЕЙСЫ (должны вернуть чистый PHP) ===")
for label, prefix, suffix in deterministic_tests:
    prompt = f"<|fim_prefix|>{prefix}<|fim_suffix|>{suffix}<|fim_middle|>"
    body = json.dumps({"model": "gemini-3.5-flash-lite", "prompt": prompt, "max_tokens": 80}).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:8089/v1/completions", data=body, headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    dt = int((time.monotonic() - t0) * 1000)
    text = data["choices"][0]["text"]
    status = "OK" if text != "" else "FAIL"
    print(f"[{status} | {dt:4d} ms] {label:46s} -> {text!r}")
