"""
mcl_errors.py
-------------
Structured representation of a syntax error / recovery event, as
specified in Phase 1 (Section 9.2):

    { expectedToken, actualToken, line, column, recoveryAction, snippet }

Keeping this as a real object (rather than a formatted string) is what
lets the later LLM diagnostic layer consume errors programmatically.
"""

from dataclasses import dataclass, asdict


@dataclass
class SyntaxErrorRecord:
    expected_token: str
    actual_token: str
    line: int
    column: int
    recovery_action: str   # e.g. "panic-mode: skipped to ';'", "phrase-level: inserted ';'"
    snippet: str

    def to_dict(self):
        return asdict(self)

    def __str__(self):
        return (
            f"[line {self.line}:{self.column}] expected {self.expected_token}, "
            f"found {self.actual_token!r} -> {self.recovery_action}\n"
            f"    {self.snippet}"
        )
