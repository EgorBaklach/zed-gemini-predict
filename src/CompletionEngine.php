<?php

declare(strict_types=1);

namespace ZedBridge;

final class CompletionEngine
{
    /**
     * @return array{text: string, rule: string}
     */
    public function complete(FimContext $ctx): array
    {
        $between = trim($ctx->currentLine());
        $above = trim($ctx->lineAbove);

        // Если между prefix и suffix (на строке курсора) и над ними только пустые разрывы строк — ничего не возвращаем
        if ($between === '' && $above === '') {
            return ['text' => '', 'rule' => 'skip:empty_line_breaks'];
        }

        // Если между ними или над ними что-то есть — предлагаем добавить символ "+"
        return ['text' => '+', 'rule' => 'local:plus_probe'];
    }
}
