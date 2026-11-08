"""Small helpers for looking at the cursor context."""


def current_line(prefix: str) -> str:
    """The part of the cursor's line that is left of the cursor."""
    return prefix.rsplit("\n", 1)[-1]


def suffix_same_line(suffix: str) -> str:
    """The part of the cursor's line that is right of the cursor."""
    return suffix.split("\n", 1)[0]


def next_code_line(suffix: str) -> str:
    """First non-blank line BELOW the cursor's line (stripped)."""
    return next((line.strip() for line in suffix.split("\n")[1:] if line.strip()), "")
