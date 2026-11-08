"""
PHP language profile: prompt + gatekeeper + ORDERED post-processing rules + fallback.

The order matters (e.g. suffix overlap must be stripped before duplicate detection, and the
paren balancer must run last on the final single-line answer). Change it only together with
tests/test_postprocessor_offline.py and a `simulate_mvc_live_coding.py --runs 3` run.
"""
from .. import rules_common as common
from ..pipeline import LanguageProfile
from . import rules as php
from .fallback import mechanical_paren_closure
from .gatekeeper import should_skip_request
from .local import close_open_block
from .prompt import SYSTEM_INSTRUCTION

RULES = (
    # 1. Remove non-code debris
    common.strip_fim_tags,
    php.strip_php_tags,
    common.strip_markdown_fences,
    php.cut_token_debris,
    common.keep_first_paragraph,
    # 2. Fit the answer between prefix and suffix
    common.strip_suffix_overlap,
    common.drop_trailing_newline_before_suffix,
    common.strip_repeated_indentation,
    common.dedupe_opening_quote,
    # 3. Structural guards against invention
    php.guard_fluent_chain,
    php.guard_control_header_body,
    php.guard_declaration_body,
    php.validate_declaration_header,
    php.keep_single_parameter,
    common.keep_line_terminator_only,
    php.drop_semicolon_after_arm,
    common.reject_argument_echo,
    common.drop_suffix_duplicate,
    # 4. Formatting and idiom fixes
    php.newline_after_open_brace,
    php.cut_after_block_closes,
    php.terminate_enum_case,
    php.convert_closure_arrow_to_block,
    # 5. Final consistency of the line
    common.strip_prefix_repetition,
    php.strip_invented_condition,
    php.balance_parens,
)

PROFILE = LanguageProfile(
    name="php",
    system_instruction=SYSTEM_INSTRUCTION,
    should_skip=should_skip_request,
    rules=RULES,
    fallback=mechanical_paren_closure,
    local_completion=close_open_block,
)
