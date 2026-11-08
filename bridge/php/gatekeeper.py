"""
Pre-flight gatekeeper: decides WITHOUT calling Gemini (0 tokens, ~2 ms) that the cursor is at a place
where any suggestion would be a guess - an "Open Semantic Slot" - or where the line is already complete.
"""
import re

from ..textutil import current_line, suffix_same_line
from .syntax import paren_depth

# Lines where no concrete expression/token has been started yet, so any completion would be
# pure semantic/architectural guessing.
OPEN_SEMANTIC_SLOT_RE = re.compile(
    r"^("
    r"\s*|"  # 1. Blank / whitespace-only line
    r"\s*[\{\}\(\)\[\];,\'\"]+\s*|"  # 2. Only bare punctuation, braces, or a bare opening quote (' or ") on the line
    r"\s*\}?\s*(?:if|elseif|else|while|for|foreach|switch|match)\s*\(?\s*\)?\s*\{?\s*|"  # 3. Bare control keyword (including `} elseif (`) without condition
    r".*(?:=|\?\?=|\.=|return)\s*(?:match|switch|fn|function)\s*\(?\s*\)?\s*\{?\s*|"  # 4. Bare `$v = match (` / `return match (` without subject
    r"\s*(?:return|echo|print|throw|throw\s+new|yield|goto|new|clone)\s*|"  # 5. Bare statement/instantiation keyword without expression
    r"\s*(?:(?:public|protected|private|final|abstract|static|readonly)\s+)*(?:function|class|interface|trait|enum)\s*|"  # 6. Bare declaration keyword without identifier
    r"\s*\$[a-zA-Z0-9_]*\s*|"  # 7. Bare `$` or `$varName` on a line before any operator (`=`, `->`, etc.) is typed
    r"\s*\$[^\n=]+?(?<![=!<>])\s*(?:=|\.=|\?\?=|\+=|-=)\s*(?:new\s*)?[\[\(\'\"]?\s*|"  # 8. Any `$var = `, `$var = [`, `$var = '`, `$this->prop = ` with nothing inside yet
    r".*(?:->|\?->|::)\s*|"  # 9. Any line ending with bare `->`, `?->`, or `::` (waiting for LSP member completion)
    r"\s*(?://|#|\*).*|"  # 10. Inside a single-line or docblock comment line
    r"\s*[a-zA-Z_][a-zA-Z0-9_]*|"  # 11. Bare partial word/keyword (`fo`, `for`, `try` without `{` or trailing space) on a line
    r"\s*[а-яА-ЯёЁ]+\s*\(?\s*\)?\s*"  # 12. Accidental Cyrillic keyboard layout typo (e.g. `ш`, `ша()`)
    r")$"
)


def should_skip_request(prefix: str, suffix: str) -> bool:
    """
    Returns True if the cursor is at an Open Semantic Slot on the current line,
    or at the end of an already-closed statement/block header,
    avoiding any LLM call (0ms, 0 tokens, zero architectural hallucination).
    """
    line = current_line(prefix)
    if OPEN_SEMANTIC_SLOT_RE.match(line):
        return True
    stripped = line.strip()
    # Completed statement ending with `;`
    # (but NOT inside an open header such as `for ($i = 0; $i < $n; ` where parens are still open)
    if stripped.endswith(";") and paren_depth(stripped) <= 0:
        return True
    # Finished array item / match arm (`'key' => $value,`)
    if stripped.endswith(",") and "=>" in stripped and paren_depth(stripped) <= 0:
        return True
    # Completed block header ending with `{` (except `try {` when catch is missing)
    if stripped.endswith("{") and not stripped.startswith("try"):
        return True
    # A closure on the current line was just closed with `}` before `);` in suffix and parens are already balanced
    same_line = suffix_same_line(suffix).strip()
    if stripped.endswith("}") and same_line.endswith(";"):
        total_open = line.count("(") + same_line.count("(")
        total_close = line.count(")") + same_line.count(")")
        if total_open == total_close:
            return True
    # The cursor is right in the middle of an identifier/keyword token (e.g. `t|ry`, `f|or`, `$v|ar`)
    if prefix and suffix and (prefix[-1].isalnum() or prefix[-1] in ("_", "$")) and (suffix[0].isalnum() or suffix[0] == "_"):
        return True
    return False
