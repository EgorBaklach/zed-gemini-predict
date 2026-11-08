"""PHP lexical helpers shared by the gatekeeper, the rules and the fallback."""
import re

PHP_STRING_RE = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"")

# Named declaration headers: classes/interfaces/traits/enums and named functions/methods (not closures)
DECLARATION_HEADER_RE = re.compile(
    r"^(?:(?:public|protected|private|static|final|abstract|readonly)\s+)*"
    r"(?:(?:class|interface|trait|enum)\s+\w+|function\s+\w+\s*\()"
)

# Lines that open a control-flow block header
CONTROL_HEADER_PREFIXES = (
    "if ", "if(", "elseif ", "elseif(", "} elseif",
    "foreach ", "foreach(", "for ", "for(", "while ", "while(",
    "catch ", "catch(", "} catch",
)

# An expression is finished right before the cursor (identifier, `)`, `]` or a closing quote)
EXPRESSION_END_RE = re.compile(r"[\w\)\]'\"]$")


def without_strings(code: str) -> str:
    """Replace PHP string literals with `''` so their content does not affect bracket counting."""
    return PHP_STRING_RE.sub("''", code)


def paren_depth(code: str) -> int:
    """Net number of open `(` in a code fragment, ignoring parentheses inside PHP string literals."""
    code = without_strings(code)
    return code.count("(") - code.count(")")
