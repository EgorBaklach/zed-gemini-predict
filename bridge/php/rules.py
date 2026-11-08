"""
PHP-specific post-processing rules (signature `(text, prefix, suffix) -> text`).
Their execution order is defined in bridge/php/__init__.py.
"""
import re

from ..textutil import current_line, next_code_line, suffix_same_line
from .syntax import (
    CONTROL_HEADER_PREFIXES,
    DECLARATION_HEADER_RE,
    EXPRESSION_END_RE,
    PHP_STRING_RE,
    paren_depth,
    without_strings,
)


def _line(prefix: str) -> str:
    """Cursor line left of the cursor, without indentation."""
    return current_line(prefix).lstrip()


def strip_php_tags(text: str, prefix: str, suffix: str) -> str:
    """A completion inside PHP code never opens/closes the PHP block (`'/'<?php`)."""
    for tag in ("<?php", "?>"):
        if tag in text:
            text = text.split(tag, 1)[0]
    return text


def cut_token_debris(text: str, prefix: str, suffix: str) -> str:
    """
    Token debris outside string literals: HTML-like tags (`)</table>`) and a dangling opening bracket
    right after a finished string or statement (`'/'[`, `$x;(`) are never intended PHP code - cut them off.
    """
    masked = PHP_STRING_RE.sub(lambda s: " " * len(s.group()), text)
    debris = re.search(r"</?[A-Za-z]", masked)
    if debris:
        return text[: debris.start()].rstrip()
    if "\n" not in text.strip():
        dangling = re.search(r"(?<=['\";])\s*[\[\(\{]\s*;?\s*$", text)
        if dangling and masked[dangling.start():].strip():  # the opener itself is not inside a string
            return text[: dangling.start()]
    return text


def guard_fluent_chain(text: str, prefix: str, suffix: str) -> str:
    """
    The fluent chain already continues on the next line (`->build();`): never extend it on this line
    with invented calls (`)->withPath(...)`) or dangling operator debris (`)>`), keep only the closure.
    """
    if not suffix_same_line(suffix).strip() and next_code_line(suffix).startswith(("->", "?->")) and "\n" not in text:
        return re.split(r"\??->", text, 1)[0].rstrip("->? ")
    return text


def guard_control_header_body(text: str, prefix: str, suffix: str) -> str:
    """A condition/loop header (`if (...`) is completed up to `{` - never with an invented body."""
    if _line(prefix).startswith(CONTROL_HEADER_PREFIXES) and "{\n" in text:
        return text.split("{\n", 1)[0] + "{"
    return text


def guard_declaration_body(text: str, prefix: str, suffix: str) -> str:
    """`final class X implements |` / `public function save(|`: complete the header only, never the body."""
    if DECLARATION_HEADER_RE.match(_line(prefix)) and "\n" in text:
        head = text.split("\n", 1)[0]
        return head.split("{", 1)[0].rstrip() + " {" if "{" in head else head
    return text


def validate_declaration_header(text: str, prefix: str, suffix: str) -> str:
    """
    Inside a declaration's parameter list (`public function getHistory(|`) the rest of the header has a
    strict grammar: `[params]) [: ?Type] [;|{]`. Debris like `?): array;` or `)?: array;` is rejected.
    """
    line = _line(prefix)
    if (
        DECLARATION_HEADER_RE.match(line)
        and paren_depth(line) > 0
        and text.strip()
        and "\n" not in text.strip()
    ):
        params, sep, rest = text.strip().partition(")")
        params_ok = not params.strip() or "$" in params
        rest_ok = re.fullmatch(r"\s*(:\s*\??[\\\w]+(\s*[|&]\s*\??[\\\w]+)*)?\s*[;{]?\s*", rest) is not None
        if sep and not (params_ok and rest_ok):
            return ""
    return text


def drop_semicolon_after_arm(text: str, prefix: str, suffix: str) -> str:
    """
    `;` is never valid after a match arm / array item (`default => 'x';`, `'key' => $v;`): those end
    with `,` or nothing. Detected structurally: the next line closes the literal or is another `=>` item.
    """
    line = _line(prefix)
    next_line = next_code_line(suffix)
    is_arm_line = (
        "=>" in line
        and not line.startswith(("return ", "$", "yield ", "foreach"))
        and not suffix_same_line(suffix).strip()
        and (next_line.startswith(("}", "]")) or "=>" in next_line)
    )
    if is_arm_line and "\n" not in text.strip() and text.lstrip().startswith(";"):
        return ""  # `;')` after a finished arm is debris, not a terminator
    if is_arm_line and "\n" not in text.strip() and text.rstrip().endswith(";") and paren_depth(line + text) <= 0:
        return text.rstrip()[:-1].rstrip()
    return text


def cut_after_block_closes(text: str, prefix: str, suffix: str) -> str:
    """
    Multi-line answer after a `{` header (`try {` -> catch skeleton): stop at the line where the
    opened block is closed again; anything after it (`return $this->...`) is an invented next statement.
    """
    if not _line(prefix).endswith("{") or "\n" not in text:
        return text
    depth = 1
    lines = text.split("\n")
    for i, line in enumerate(lines):
        code = without_strings(line)
        depth += code.count("{") - code.count("}")
        if depth <= 0 and i < len(lines) - 1:
            return "\n".join(lines[: i + 1])
    return text


def keep_single_parameter(text: str, prefix: str, suffix: str) -> str:
    """
    Promoted constructor parameter (`private readonly |`): complete THIS parameter only.
    Extra lines are invented dependencies (`private readonly OrderRepositoryInterface $repository`).
    """
    if re.match(r"^(?:public|protected|private)\b", _line(prefix)) and "\n" in text.strip():
        return text.lstrip("\n").split("\n", 1)[0].rstrip()
    return text


def newline_after_open_brace(text: str, prefix: str, suffix: str) -> str:
    """Body / closing part after a `{` header starts on a new line (`try {` + `} catch (...)`)."""
    if _line(prefix).endswith("{") and "\n" in text and text[:1] in (" ", "\t", "}"):
        return "\n" + text
    return text


def terminate_enum_case(text: str, prefix: str, suffix: str) -> str:
    """`case Name = 'val'` gets its `;` unless the suffix already has it."""
    line = _line(prefix)
    if line.startswith("case ") and "=" in line and text and not text.rstrip().endswith(";") and not suffix.lstrip(" \t").startswith(";"):
        return text.rstrip() + ";"
    return text


def convert_closure_arrow_to_block(text: str, prefix: str, suffix: str) -> str:
    """After `function (...) use (` the model sometimes writes `=> expr` - PHP needs `{ return expr; }`."""
    line = _line(prefix)
    if "function" in line and "use (" in line and ") => " in text and "{" not in text:
        var_part, expr_part = text.split(") => ", 1)
        expr_clean = expr_part.rstrip("; ")
        indent = current_line(prefix)
        leading_ws = indent[: len(indent) - len(indent.lstrip())]
        return f"{var_part}) {{\n{leading_ws}    return {expr_clean};\n{leading_ws}}}"
    return text


def strip_invented_condition(text: str, prefix: str, suffix: str) -> str:
    """Closing `if (...` with `) && $new > 0 {` invents a condition - keep only `) {`."""
    if not text or "\n" in text:
        return text
    if (
        _line(prefix).startswith(("if ", "if(", "elseif ", "elseif(", "} elseif", "while ", "while("))
        and text.startswith(")")
        and (" && " in text or " || " in text)
        and text.rstrip().endswith("{")
    ):
        return ") {"
    return text


def balance_parens(text: str, prefix: str, suffix: str) -> str:
    """Make `(`/`)` of the whole line (prefix + answer + same-line suffix) balanced; string literals are ignored."""
    if not text or "\n" in text:
        return text

    same_line = suffix_same_line(suffix).strip()
    open_parens = paren_depth(current_line(prefix))
    suffix_net_close = max(0, -paren_depth(same_line))
    text_no_strings = without_strings(text)
    added_open = text_no_strings.count("(")
    added_close = text_no_strings.count(")")
    needed_close = max(0, open_parens + added_open - suffix_net_close)

    if same_line:
        # The statement terminator already exists after the cursor (`, $this->results);`): never add another `;`
        if same_line.rstrip().endswith((";", "{")) and text.rstrip().endswith(";"):
            text = text.rstrip()[:-1]
        while added_close > needed_close and text.endswith(")"):
            text = text[:-1]
            added_close -= 1
        # The same-line suffix continues an OUTER call (e.g. `sprintf(..., X` + `, $result);`):
        # an inner call left open by the model must be closed, otherwise the line can never parse.
        if added_close < needed_close and EXPRESSION_END_RE.search(text):
            text += ")" * (needed_close - added_close)
    else:
        while added_close > needed_close and (text.endswith("))") or text.endswith("));")):
            if text.endswith("));"):
                text = text[:-2] + ";"
            else:
                text = text[:-1]
            added_close -= 1

        # Add missing ')' if the model closed a line with ') {' or ');' but under-counted nested parens
        if 0 < added_close < needed_close:
            missing = ")" * (needed_close - added_close)
            if text.endswith(") {"):
                text = text[:-2] + missing + " {"
            elif text.endswith("){"):
                text = text[:-1] + missing + "{"
            elif text.endswith(");"):
                text = text[:-1] + missing + ";"

    return text
