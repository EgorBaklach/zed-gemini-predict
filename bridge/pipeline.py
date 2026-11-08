"""
Completion pipeline: language profile + ordered post-processing rules.

    Zed request -> profile.should_skip (gatekeeper, 0 tokens)
                -> Gemini
                -> profile.rules, applied in order (each rule: (text, prefix, suffix) -> text)
                -> profile.fallback if nothing is left

Every rule that changed the text is reported by name, so the debug log shows WHY an answer looks the way it does.
"""
from dataclasses import dataclass
from typing import Callable

Rule = Callable[[str, str, str], str]


@dataclass(frozen=True)
class LanguageProfile:
    name: str
    system_instruction: str
    should_skip: Callable[[str, str], bool]
    rules: tuple[Rule, ...]
    fallback: Callable[[str, str], str]


def postprocess(raw: str, prefix: str, suffix: str, profile: LanguageProfile) -> tuple[str, list[str]]:
    """Apply the profile's rules in order; returns the final text and the names of the rules that changed it."""
    text, applied = raw, []
    for rule in profile.rules:
        if not text:  # every rule keeps an empty answer empty
            break
        new = rule(text, prefix, suffix)
        if new != text:
            applied.append(rule.__name__)
            text = new
    if not text:
        fallback = profile.fallback(prefix, suffix)
        if fallback:
            applied.append(f"fallback:{profile.fallback.__name__}")
            text = fallback
    return text, applied
