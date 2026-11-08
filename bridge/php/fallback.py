"""Deterministic fallback used when Gemini returns nothing (or everything was filtered out)."""
from ..textutil import current_line, next_code_line, suffix_same_line
from .syntax import EXPRESSION_END_RE, paren_depth


def mechanical_paren_closure(prefix: str, suffix: str) -> str:
    """
    If an expression is finished right before the cursor and the code after the cursor continues
    the same statement (same-line suffix like ` . '.php';` or a fluent `->build();` on the next line),
    the only valid minimal insertion is closing the still-open parentheses.
    """
    line = current_line(prefix)
    if not EXPRESSION_END_RE.search(line):
        return ""
    same_line = suffix_same_line(suffix)
    continues_statement = bool(same_line.strip()) or next_code_line(suffix).startswith(("->", "?->"))
    if not continues_statement:
        return ""
    missing = paren_depth(line) + min(0, paren_depth(same_line))
    return ")" * missing if missing > 0 else ""
