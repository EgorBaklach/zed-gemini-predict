<?php

declare(strict_types=1);

namespace ZedBridge;

final readonly class FimContext
{
    public string $currentLinePrefix;
    public string $currentLineSuffix;
    public string $lineAbove;
    public string $lineBelow;

    public function __construct(
        public string $prefix,
        public string $suffix,
    ) {
        $prefixLines = explode("\n", $this->prefix);
        $suffixLines = explode("\n", $this->suffix);

        $lastIdx = count($prefixLines) - 1;
        $this->currentLinePrefix = $prefixLines[$lastIdx];
        $this->lineAbove = $lastIdx > 0 ? $prefixLines[$lastIdx - 1] : '';

        $this->currentLineSuffix = $suffixLines[0];
        $this->lineBelow = count($suffixLines) > 1 ? $suffixLines[1] : '';
    }

    public function currentLine(): string
    {
        return $this->currentLinePrefix . $this->currentLineSuffix;
    }
}
