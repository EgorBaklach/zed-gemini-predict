<?php

declare(strict_types=1);

use ZedBridge\CompletionEngine;
use ZedBridge\FimParser;

spl_autoload_register(static function (string $class): void {
    $prefix = 'ZedBridge\\';
    if (!str_starts_with($class, $prefix)) {
        return;
    }
    $relative = substr($class, strlen($prefix));
    $file = __DIR__ . '/../src/' . str_replace('\\', '/', $relative) . '.php';
    if (is_file($file)) {
        require $file;
    }
});

$engine = new CompletionEngine();

$cases = [
    'empty_file' => [
        'prompt' => '<|fim_prefix|><|fim_suffix|><|fim_middle|>',
        'expected' => '',
    ],
    'empty_line_breaks_between_prefix_and_suffix' => [
        'prompt' => "<|fim_prefix|><?php\n\n   <|fim_suffix|>   \n}\n<|fim_middle|>",
        'expected' => '',
    ],
    'code_between_prefix_and_suffix_in_prefix' => [
        'prompt' => "<|fim_prefix|><?php\n\n\$a = 1<|fim_suffix|>\n<|fim_middle|>",
        'expected' => '+',
    ],
    'code_between_prefix_and_suffix_in_suffix' => [
        'prompt' => "<|fim_prefix|><?php\n\n   <|fim_suffix|>return \$a;\n<|fim_middle|>",
        'expected' => '+',
    ],
    'code_above_empty_current_line' => [
        'prompt' => "<|fim_prefix|><?php\n\$a = 1;\n<|fim_suffix|>\n<|fim_middle|>",
        'expected' => '+',
    ],
];

$passed = 0;
foreach ($cases as $name => $case) {
    $ctx = FimParser::parse($case['prompt']);
    $res = $engine->complete($ctx);
    if ($res['text'] !== $case['expected']) {
        fwrite(STDERR, sprintf(
            "[FAIL] %s: expected %s, got %s (rule=%s)\n",
            $name,
            json_encode($case['expected']),
            json_encode($res['text']),
            $res['rule']
        ));
        exit(1);
    }
    $passed++;
    echo sprintf("[PASS] %s -> %s (%s)\n", $name, json_encode($res['text']), $res['rule']);
}

echo sprintf("\nAll %d PHP bridge tests passed.\n", $passed);
