import json
import time
import urllib.request

cases = [
    (
        "1. Условие if + вложенные скобки",
        "<?php\nif (isset($user['id']) && !empty($user['email']",
        "\n    $isValid = true;\n}"
    ),
    (
        "2. Элемент ассоциативного массива перед закрывающей ];",
        "<?php\n$payload = [\n    'user_id' => $userId,\n    'email' => $email,\n    'is_active' => ",
        "\n];\nreturn $payload;"
    ),
    (
        "3. Рефакторинг fn() => в анонимную function() use ()",
        "<?php\n$taxRate = 0.2;\n// $prices = array_map(fn($item) => $item['price'] * (1 + $taxRate), $items);\n$prices = array_map(function ($item) use (",
        ", $items);"
    ),
    (
        "4. Обратный рефакторинг: function() use () в стрелочную fn() =>",
        "<?php\n$prefix = 'ID_';\n// $ids = array_map(function ($row) use ($prefix) { return $prefix . $row['id']; }, $rows);\n$ids = array_map(fn($row) => ",
        ", $rows);"
    ),
    (
        "5. Конструкция try / catch (начало блока catch)",
        "<?php\ntry {\n    $db->beginTransaction();\n    $db->execute($query);\n    $db->commit();\n} catch (",
        "\n    $db->rollBack();\n    throw $e;\n}"
    ),
    (
        "6. Конструкция try / catch с нуля (открытие try и шаблон catch)",
        "<?php\ntry {",
        "\n"
    ),
    (
        "7. Объявление класса (implements интерфейса + открытие тела)",
        "<?php\nnamespace App\\Services;\n\ninterface PaymentGatewayInterface {\n    public function charge(int $amount): bool;\n}\n\nfinal class StripeGateway implements ",
        "\n}"
    ),
    (
        "8. Объявление интерфейса (сигнатура метода без тела)",
        "<?php\nnamespace App\\Contracts;\n\ninterface UserRepositoryInterface\n{\n    public function findById(int $id): ?array;\n    public function save(array $data",
        "\n}"
    ),
    (
        "9. Конструктор PHP 8 (Constructor Property Promotion)",
        "<?php\nfinal class OrderService\n{\n    public function __construct(\n        private readonly LoggerInterface $logger,\n        private readonly ",
        "\n    ) {}\n}"
    ),
    (
        "10. Цикл foreach (ключ => значение)",
        "<?php\n$result = [];\nforeach ($users as $userId => ",
        "\n    $result[$userId] = $user['name'];\n}"
    ),
    (
        "11. Цикл for (классический счетчик)",
        "<?php\n$count = count($items);\nfor ($i = 0; $i < $count; ",
        "\n    process($items[$i]);\n}"
    ),
    (
        "12. Встроенная функция PHP: sprintf (закрытие аргументов)",
        "<?php\n$msg = sprintf('User #%d (%s) logged in from %s', $userId, $userName, ",
        "\n$logger->info($msg);"
    ),
    (
        "13. Встроенная функция PHP: array_filter с замыканием",
        "<?php\n$activeUsers = array_filter($users, fn(array $u): bool => ",
        "\n"
    ),
    (
        "14. Встроенная функция PHP: json_decode с флагами",
        "<?php\n$data = json_decode($rawJson, true, 512, ",
        "\n"
    ),
    (
        "15. Выражение match (PHP 8)",
        "<?php\n$label = match ($status) {\n    'pending' => 'В ожидании',\n    'paid' => 'Оплачен',\n    default => ",
        "\n};"
    ),
    (
        "16. Конкатенация строк с точками и методом",
        "<?php\n$fullPath = rtrim($baseDir, '/') . '/' . ltrim($fileName",
        "\nreturn $fullPath;"
    ),
]

total_ms = 0
for title, prefix, suffix in cases:
    prompt = f"<|fim_prefix|>{prefix}<|fim_suffix|>{suffix}<|fim_middle|>"
    body = json.dumps({
        "model": "gemini-3.5-flash-lite",
        "prompt": prompt,
        "max_tokens": 80,
        "stop": ["<|endoftext|>"]
    }).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8089/v1/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    dt = int((time.time() - t0) * 1000)
    total_ms += dt
    text = data["choices"][0]["text"]
    usage = data["usage"]
    print(f"[{dt:4d} ms | +{usage['completion_tokens']:2d} tok] {title}")
    print(f"   >>> {text!r}\n")

print(f"Среднее время ответа по {len(cases)} кейсам: {total_ms // len(cases)} мс")
