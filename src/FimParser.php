<?php

declare(strict_types=1);

namespace ZedBridge;

final class FimParser
{
    /** @var array<int, array{string, string, string}> */
    private const array FORMATS = [
        ['<|fim_prefix|>', '<|fim_suffix|>', '<|fim_middle|>'],
        ['<fim_prefix>', '<fim_suffix>', '<fim_middle>'],
        ['[SUFFIX]', '[PREFIX]', ''],
    ];

    public static function parse(string $prompt): FimContext
    {
        foreach (self::FORMATS as [$prefixTag, $suffixTag, $middleTag]) {
            if (!str_contains($prompt, $prefixTag) || !str_contains($prompt, $suffixTag)) {
                continue;
            }

            if ($prefixTag === '[SUFFIX]') {
                [, $rest] = explode('[SUFFIX]', $prompt, 2);
                [$suffix, $prefix] = explode('[PREFIX]', $rest, 2);
                return new FimContext($prefix, $suffix);
            }

            [, $afterPrefix] = explode($prefixTag, $prompt, 2);
            [$prefix, $afterSuffix] = explode($suffixTag, $afterPrefix, 2);
            $suffix = $middleTag !== '' && str_contains($afterSuffix, $middleTag)
                ? explode($middleTag, $afterSuffix, 2)[0]
                : $afterSuffix;

            return new FimContext($prefix, $suffix);
        }

        return new FimContext($prompt, '');
    }
}
