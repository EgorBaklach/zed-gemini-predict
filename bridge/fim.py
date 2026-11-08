"""Fill-In-the-Middle prompt format: parsing Zed's prompt and building the one sent to Gemini."""

FIM_PREFIX = "<|fim_prefix|>"
FIM_SUFFIX = "<|fim_suffix|>"
FIM_MIDDLE = "<|fim_middle|>"
END_OF_TEXT = "<|endoftext|>"

# `<|fim_middle|>` is deliberately NOT a stop sequence: Gemini sometimes echoes it first and
# would then stop with an empty answer. It is stripped by the post-processor instead.
STOP_SEQUENCES = [FIM_SUFFIX, FIM_PREFIX, END_OF_TEXT]


def parse_fim_prompt(prompt: str) -> tuple[str, str]:
    """Split a FIM prompt (Qwen `<|fim_*|>`, StarCoder `<fim_*>` or Codestral `[SUFFIX]/[PREFIX]`) into prefix and suffix."""
    if FIM_PREFIX in prompt and FIM_SUFFIX in prompt:
        after_pre = prompt.split(FIM_PREFIX, 1)[1]
        prefix, after_suf = after_pre.split(FIM_SUFFIX, 1)
        suffix = after_suf.split(FIM_MIDDLE, 1)[0]
        return prefix, suffix
    if "<fim_prefix>" in prompt and "<fim_suffix>" in prompt:
        after_pre = prompt.split("<fim_prefix>", 1)[1]
        prefix, after_suf = after_pre.split("<fim_suffix>", 1)
        suffix = after_suf.split("<fim_middle>", 1)[0]
        return prefix, suffix
    if "[SUFFIX]" in prompt and "[PREFIX]" in prompt:
        after_suf = prompt.split("[SUFFIX]", 1)[1]
        suffix, prefix = after_suf.split("[PREFIX]", 1)
        return prefix, suffix
    return prompt, ""


def build_fim_prompt(prefix: str, suffix: str) -> str:
    return f"{FIM_PREFIX}{prefix}{FIM_SUFFIX}{suffix}{FIM_MIDDLE}"
