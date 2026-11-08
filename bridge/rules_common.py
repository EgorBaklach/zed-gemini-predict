"""
Language-agnostic post-processing rules.

Every rule has the signature `(text, prefix, suffix) -> text` and must keep an empty text empty.
The ORDER in which rules run is defined by the language profile (e.g. bridge/php/__init__.py).
"""
import re

from .fim import END_OF_TEXT, FIM_MIDDLE, FIM_PREFIX, FIM_SUFFIX
from .textutil import current_line, suffix_same_line


def strip_fim_tags(text: str, prefix: str, suffix: str) -> str:
    """Drop a leading echoed `<|fim_middle|>` and cut everything after any leaked FIM / EOS tag."""
    for lead in (FIM_MIDDLE, "<fim_middle>"):
        if text.startswith(lead):
            text = text[len(lead):]
    for tag in (FIM_SUFFIX, FIM_PREFIX, FIM_MIDDLE, END_OF_TEXT):
        if tag in text:
            text = text.split(tag, 1)[0]
    return text


def strip_markdown_fences(text: str, prefix: str, suffix: str) -> str:
    """```lang ... ``` wrappers are prose formatting, not code."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1])
        if len(lines) >= 2:
            return "\n".join(lines[1:])
    return text


def keep_first_paragraph(text: str, prefix: str, suffix: str) -> str:
    """Single-construct horizon: a blank line means the model started the NEXT construct - cut it."""
    if "\n\n" in text:
        first_part = text.split("\n\n", 1)[0]
        if first_part.strip():
            return first_part
    return text


def strip_suffix_overlap(text: str, prefix: str, suffix: str) -> str:
    """Remove a tail of the answer that repeats the beginning of the suffix (`$x);` + suffix `);`)."""
    if not text or not suffix:
        return text

    max_k = min(len(text), len(suffix))
    for k in range(max_k, 1, -1):
        if text.endswith(suffix[:k]):
            candidate = text[:-k]
            if candidate.strip():
                return candidate

    suffix_lstripped = suffix.lstrip(" \t\r\n")
    if suffix_lstripped:
        first_line = suffix_lstripped.splitlines()[0]
        max_k2 = min(len(text), len(first_line))
        for k in range(max_k2, 1, -1):
            overlap = first_line[:k]
            if overlap.strip() and text.endswith(overlap):
                candidate = text[:-k]
                if candidate.strip():
                    return candidate

    return text


def drop_trailing_newline_before_suffix(text: str, prefix: str, suffix: str) -> str:
    """The suffix already starts with a newline - do not add an empty line."""
    if suffix.startswith("\n") and text.endswith("\n"):
        text = text[:-1]
        if text.endswith("\r"):
            text = text[:-1]
    return text


def strip_repeated_indentation(text: str, prefix: str, suffix: str) -> str:
    """Cursor on an indented blank line and the answer repeats that indentation."""
    line = current_line(prefix)
    if line and line.isspace() and text.startswith(line):
        return text[len(line):]
    return text


def dedupe_opening_quote(text: str, prefix: str, suffix: str) -> str:
    """Prefix ends with a quote and the answer opens the same quote again (`''key'`)."""
    if prefix.endswith(("'", '"')) and len(text) >= 2 and text[0] == prefix[-1] and text[1].isalnum():
        return text[1:]
    return text


def keep_line_terminator_only(text: str, prefix: str, suffix: str) -> str:
    """A complete line must not grow new lines: `,\\n    Operation::Power => ...` invents a new case. Keep only `,`/`;`."""
    m = re.match(r"^([,;])[ \t]*\n", text)
    if m and current_line(prefix).lstrip():
        return m.group(1)
    return text


_STRING_LITERAL_RE = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"")


def _open_call_arguments(line: str) -> list[str]:
    """Top-level arguments already written inside the innermost still-open `(` of the line (strings masked)."""
    line = _STRING_LITERAL_RE.sub("''", line)
    depth, start = 0, None
    for i in range(len(line) - 1, -1, -1):
        ch = line[i]
        if ch == ")":
            depth += 1
        elif ch == "(":
            if depth == 0:
                start = i + 1
                break
            depth -= 1
    if start is None:
        return []
    args, level, current = [], 0, ""
    for ch in line[start:]:
        if ch in "([{":
            level += 1
        elif ch in ")]}":
            level -= 1
        if ch == "," and level == 0:
            args.append(current.strip())
            current = ""
        else:
            current += ch
    return [a for a in args if a]


def reject_argument_echo(text: str, prefix: str, suffix: str) -> str:
    """
    `f($a, $op->value, $b, |` -> `$b` / `$op` repeats a value already passed to this call
    (or the base of one: `$op` of `$op->value`). Silence beats wrong code.
    """
    line = current_line(prefix).lstrip()
    if not re.search(r",\s*$", line) or not text.strip():
        return text
    core = text.strip().rstrip(";").rstrip(")").strip()
    if not core:
        return text
    for arg in _open_call_arguments(line):
        if core == arg or arg.startswith((core + "->", core + "?->", core + "[")):
            return ""
    return text


def drop_suffix_duplicate(text: str, prefix: str, suffix: str) -> str:
    """The whole answer already follows the cursor (`));` before `));`, or `};` that is the next line)."""
    stripped = text.strip()
    if stripped and "\n" not in stripped:
        if suffix.lstrip(" \t").startswith(stripped) or (
            not suffix_same_line(suffix).strip() and suffix.lstrip().startswith(stripped)
        ):
            return ""
    return text


def strip_prefix_repetition(text: str, prefix: str, suffix: str) -> str:
    """The answer repeats what is already typed on the cursor's line."""
    if not text or not prefix:
        return text
    line = current_line(prefix).strip()
    if len(line) >= 6:
        text_stripped = text.strip(" ()")
        # A pure closer like `)` / `))` is never a repetition (empty string would match any line end)
        if text_stripped and (text_stripped == line or line.endswith(text_stripped)):
            return ""
    return text
