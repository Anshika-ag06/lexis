"""
mcl_check.py
------------
One function, `check_source`, that runs a piece of MCL source through the
whole front end (lexer -> parser -> semantic analyzer) and reports every
problem in one structured result.

Phase 3 uses this as the *verifier* in three places, so they can never
disagree about what "valid" means:
    * build_dataset.py   - keeps a corrupted program only if it really fails
    * evaluate_model.py  - a model's fix counts only if it passes
    * mcl_repair.py      - the self-validating fix loop

Semantic analysis is only run when there are no syntax errors, because
semantic errors reported on a half-recovered tree are mostly noise.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from mcl_lexer import Lexer, LexicalError
from mcl_parser import Parser
from mcl_semantic import SemanticAnalyzer


@dataclass
class CheckResult:
    source: str
    lex_error: Optional[LexicalError] = None
    syntax_errors: list = field(default_factory=list)
    semantic_errors: list = field(default_factory=list)
    ast: object = None

    @property
    def ok(self) -> bool:
        return self.lex_error is None and not self.syntax_errors and not self.semantic_errors

    @property
    def error_count(self) -> int:
        return (1 if self.lex_error else 0) + len(self.syntax_errors) + len(self.semantic_errors)

    def diagnostics(self) -> List[dict]:
        """Every problem as a plain dict (JSON-friendly)."""
        out: List[dict] = []
        if self.lex_error is not None:
            out.append({
                "kind": "lexical",
                "message": self.lex_error.message,
                "line": self.lex_error.line,
                "column": self.lex_error.column,
            })
        out.extend(e.to_dict() for e in self.syntax_errors)
        out.extend(e.to_dict() for e in self.semantic_errors)
        return out


def check_source(source: str) -> CheckResult:
    try:
        tokens = Lexer(source).tokenize()
    except LexicalError as e:
        return CheckResult(source=source, lex_error=e)

    parser = Parser(tokens, source)
    ast = parser.parse_program()
    result = CheckResult(source=source, syntax_errors=list(parser.errors), ast=ast)
    if not parser.errors:
        result.semantic_errors = list(SemanticAnalyzer(source).analyze(ast))
    return result
