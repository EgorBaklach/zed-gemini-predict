<?php

declare(strict_types=1);

use ZedBridge\CompletionEngine;
use ZedBridge\FimParser;

spl_autoload_register( static function (string $class): void {
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

$uri = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';
$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';

if ($method !== 'POST' || !str_starts_with($uri, '/v1/completions')) {
    http_response_code(404);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(['error' => 'Not Found']);
    exit;
}

$rawBody = (string) file_get_contents('php://input');
$payload = json_decode($rawBody, true);

if (!is_array($payload)) {
    http_response_code(400);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(['error' => 'Invalid JSON payload']);
    exit;
}

$prompt = (string) ($payload['prompt'] ?? '');
$model = (string) ($payload['model'] ?? 'php-syntax-local');

$ctx = FimParser::parse($prompt);
$engine = new CompletionEngine();
$result = $engine->complete($ctx);

$debugLogPath = getenv('ZED_PROXY_DEBUG_LOG') ?: '/tmp/zed_fim_debug.log';
$logEntry = [
    'ts' => time(),
    'rule' => $result['rule'],
    'line_above' => $ctx->lineAbove,
    'line_prefix' => $ctx->currentLinePrefix,
    'line_suffix' => $ctx->currentLineSuffix,
    'text' => $result['text'],
];
@file_put_contents(
    $debugLogPath,
    json_encode($logEntry, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) . "\n",
    FILE_APPEND
);

$now = time();
$response = [
    'id' => 'cmpl-' . (int) (microtime(true) * 1000),
    'object' => 'text_completion',
    'created' => $now,
    'model' => $model,
    'choices' => [
        [
            'text' => $result['text'],
            'finish_reason' => 'stop',
        ],
    ],
    'usage' => [
        'prompt_tokens' => 0,
        'completion_tokens' => 0,
        'total_tokens' => 0,
    ],
];

header('Content-Type: application/json; charset=utf-8');
echo json_encode($response, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
