"""
Local (deterministic) completions computed WITHOUT Gemini: 0 tokens, ~1 ms, no nondeterminism.
They run before the gatekeeper, because they apply exactly where the gatekeeper would stay silent
(end of a finished statement, blank line).
"""
import re

from ..textutil import suffix_same_line
from .syntax import without_strings

_COMMENT_RE = re.compile(r"(//|#(?!\[)).*$")


def _indent(line: str) -> int:
    ws = line[: len(line) - len(line.lstrip())]
    return len(ws.expandtabs(4))


def _innermost_unclosed_brace(lines: list[str]) -> int | None:
    """Index of the line holding the innermost `{` that is not closed within `lines` (strings/comments ignored)."""
    stack: list[int] = []
    for i, line in enumerate(lines):
        code = _COMMENT_RE.sub("", without_strings(line))
        for ch in code:
            if ch == "{":
                stack.append(i)
            elif ch == "}" and stack:
                stack.pop()
    return stack[-1] if stack else None


def close_open_block(prefix: str, suffix: str) -> str:
    """
    The developer opened a block and wrote its body, but the closing `}` is missing:

            if (!$ok)
            {
                return $error;|          <- cursor at the end of the body line (or on a blank line below it)
            return $result;              <- next code is back at the `{` indentation level and is not `}`

    -> suggest `\\n        }` (at end of line) or `}` (on a blank line indented like the `{`).
    The block counts as unclosed only by structure: braces + indentation, never by meaning.
    """
    if suffix_same_line(suffix).strip():
        return ""  # cursor is not at the end of the line
    lines = prefix.split("\n")
    current = lines[-1]
    at_line_end = bool(current.strip())
    if at_line_end and not current.rstrip().endswith((";", "}")):
        return ""  # the statement on the cursor line is not finished yet

    opener = _innermost_unclosed_brace(lines)
    if opener is None or opener == len(lines) - 1:
        return ""
    opener_indent = _indent(lines[opener])
    body = [line for line in lines[opener + 1:] if line.strip()]
    if not body or any(_indent(line) <= opener_indent for line in body):
        return ""  # empty block (open slot) or body not indented inside the block

    next_line = next((line for line in suffix.split("\n")[1:] if line.strip()), "")
    if not next_line:
        return ""
    next_indent = _indent(next_line)
    if next_indent > opener_indent:
        return ""  # the block continues below
    if next_indent == opener_indent and next_line.strip().startswith("}"):
        return ""  # already closed (`}`, `} else {`, `} catch (...) {`)

    ws = lines[opener][: len(lines[opener]) - len(lines[opener].lstrip())]
    if at_line_end:
        return f"\n{ws}}}"
    return "}" if _indent(current) == opener_indent else ""
