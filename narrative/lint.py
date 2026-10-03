"""Lint check: clue text must contain facts, not instructions (HANDOVER §6.5).

A clue never addresses the reader or tells anyone what to do. This rejects
imperative / prompt-injection-like phrasing so the False-Belief Attack stays a
"consistent facts" defense, distinct from the Mantis-style injection baseline
(D1), which deliberately *does* contain instructions and therefore lives in
baselines/ and bypasses this lint.
"""
from __future__ import annotations

import re

# Phrases that signal an instruction to, or address of, the reader/agent.
BANNED_PATTERNS = [
    r"\bignore\b", r"\byou must\b", r"\byou should\b", r"\bplease\b",
    r"\bassistant\b", r"\bsystem\s*:", r"\bsystem note\b", r"\bnotice to\b",
    r"\bprevious instructions?\b", r"\breport it\b", r"\bstop scanning\b",
    r"\bdo not\b", r"\bmust not\b", r"\bas an ai\b", r"\bprompt\b",
    r"\binstruction", r"\boverride\b", r"\bdisregard\b",
    r"\byour task\b", r"\bthe only production\b", r"\breport .* and stop\b",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in BANNED_PATTERNS]


class LintError(ValueError):
    pass


def lint_no_instructions(text: str) -> None:
    """Raise LintError if ``text`` reads like an instruction rather than a fact."""
    for rx in _COMPILED:
        m = rx.search(text)
        if m:
            raise LintError(f"instruction-like phrase {m.group(0)!r} in clue content")


def is_clean(text: str) -> bool:
    try:
        lint_no_instructions(text)
        return True
    except LintError:
        return False
