import json
import time
import urllib.request

cases = [
    (
        "17. Backed Enum (PHP 8.1+): завершение case по образцу",
        "<?php\ndeclare(strict_types=1);\n\nenum OrderStatus: string\n{\n    case Pending = 'pending';\n    case Paid = 'paid';\n    case Cancelled = ",
        "\n}"
    ),
    (
        "18. Trait: объявление метода внутри трейта",
        "<?php\ndeclare(strict_types=1);\n\ntrait TimestampsTrait\n{\n    private ?\\DateTimeImmutable $createdAt = null;\n\n    public function getCreatedAt(",
        "\n    {\n        return $this->createdAt;\n    }\n}"
    ),
    (
        "19. Fluent Method Chain (например, в миграции или QueryBuilder)",
        "<?php\n$table->string('email', 255)->unique()->nullable(",
        "\n$table->timestamps();"
    ),
    (
        "20. Nullsafe цепочка (?->) + Null coalescing (??)",
        "<?php\n$cityName = $user?->getProfile()?->getAddress()?->getCity(",
        "\nreturn $cityName;"
    ),
]

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
    text = data["choices"][0]["text"]
    usage = data["usage"]
    print(f"[{dt:4d} ms | +{usage['completion_tokens']:2d} tok] {title}")
    print(f"   >>> {text!r}\n")
