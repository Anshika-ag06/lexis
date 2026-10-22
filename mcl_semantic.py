"""
mcl_semantic.py
----------------
Semantic analyzer for MCL (Phase 2, Section 10.2 - Semantic Analysis).

Performs, in one traversal of the AST produced by mcl_parser.Parser:
    * Scope checking        - if/while bodies each get their own scope
    * Declaration checking  - no redeclaration within the same scope
    * Reference checking    - no use of an undeclared identifier
    * Type checking         - int/bool are checked at every expression
                              and every place a value is consumed (decl
                              initializer, assignment RHS, if/while
                              condition, arithmetic/relational/logical
                              operands)

Like the parser's own panic-mode/phrase-level recovery, semantic
analysis here does not stop at the first mistake: every problem is
recorded as a SemanticErrorRecord and the analyzer keeps walking the
rest of the tree. Any expression whose type could not be determined
resolves to the sentinel type "error", which is treated as compatible
with everything else - this stops one real mistake (e.g. an undeclared
variable) from generating a cascade of spurious follow-on errors every
place that variable is subsequently used.
"""

from dataclasses import asdict, dataclass
from typing import List, Optional

from mcl_ast import (
    Assign, BinaryOp, Decl, ErrorNode, Identifier, If, Literal, Node,
    Print, Program, While,
)
from mcl_symtable import SymbolTable

ARITHMETIC_OPS = {"+", "-", "*", "/"}
COMPARISON_OPS = {"<", ">", "<=", ">=", "==", "!="}
LOGICAL_OPS = {"&&", "||"}


@dataclass
class SemanticErrorRecord:
    kind: str            # "redeclaration" | "undeclared" | "type-mismatch"
    message: str
    line: int
    column: int
    snippet: str

    def to_dict(self):
        return asdict(self)

    def __str__(self):
        return f"[line {self.line}] {self.kind}: {self.message}\n    {self.snippet}"


class SemanticAnalyzer:
    def __init__(self, source: str = ""):
        self.symtab = SymbolTable()
        self.errors: List[SemanticErrorRecord] = []
        self.source_lines = source.splitlines()

    def _snippet(self, line: int) -> str:
        return self.source_lines[line - 1] if 0 < line <= len(self.source_lines) else ""

    def _error(self, kind: str, message: str, line: int, column: int = 1) -> None:
        self.errors.append(SemanticErrorRecord(kind, message, line, column, self._snippet(line)))

    # -- entry point -----------------------------------------------------
    def analyze(self, program: Program) -> List[SemanticErrorRecord]:
        for stmt in program.statements:
            self._stmt(stmt)
        return self.errors

    # -- statements --------------------------------------------------------
    def _stmt(self, node: Optional[Node]) -> None:
        if node is None or isinstance(node, ErrorNode):
            return  # already reported by the parser; don't double-report
        if isinstance(node, Decl):
            self._decl(node)
        elif isinstance(node, Assign):
            self._assign(node)
        elif isinstance(node, If):
            self._if(node)
        elif isinstance(node, While):
            self._while(node)
        elif isinstance(node, Print):
            self._print(node)

    def _decl(self, node: Decl) -> None:
        expr_type = self._expr(node.expr)
        existing = self.symtab.declare(node.name, node.var_type, node.line)
        if existing is not None:
            self._error(
                "redeclaration",
                f"'{node.name}' already declared at line {existing.line}",
                node.line,
            )
        elif expr_type not in (node.var_type, "error"):
            self._error(
                "type-mismatch",
                f"cannot initialize {node.var_type} variable '{node.name}' with a {expr_type} value",
                node.line,
            )

    def _assign(self, node: Assign) -> None:
        expr_type = self._expr(node.expr)
        sym = self.symtab.lookup(node.name)
        if sym is None:
            self._error("undeclared", f"'{node.name}' is not declared", node.line)
        elif expr_type not in (sym.type, "error"):
            self._error(
                "type-mismatch",
                f"cannot assign a {expr_type} value to {sym.type} variable '{node.name}'",
                node.line,
            )

    def _if(self, node: If) -> None:
        cond_type = self._expr(node.cond)
        if cond_type not in ("bool", "error"):
            self._error("type-mismatch", f"if condition must be bool, got {cond_type}", node.line)
        self.symtab.enter_scope()
        for s in node.then_block:
            self._stmt(s)
        self.symtab.exit_scope()
        if node.else_block is not None:
            self.symtab.enter_scope()
            for s in node.else_block:
                self._stmt(s)
            self.symtab.exit_scope()

    def _while(self, node: While) -> None:
        cond_type = self._expr(node.cond)
        if cond_type not in ("bool", "error"):
            self._error("type-mismatch", f"while condition must be bool, got {cond_type}", node.line)
        self.symtab.enter_scope()
        for s in node.body:
            self._stmt(s)
        self.symtab.exit_scope()

    def _print(self, node: Print) -> None:
        self._expr(node.expr)

    # -- expressions: return the inferred type, "error" on failure --------
    def _expr(self, node: Optional[Node]) -> str:
        if node is None or isinstance(node, ErrorNode):
            return "error"
        if isinstance(node, Literal):
            return node.kind
        if isinstance(node, Identifier):
            sym = self.symtab.lookup(node.name)
            if sym is None:
                self._error("undeclared", f"'{node.name}' is not declared", node.line)
                return "error"
            return sym.type
        if isinstance(node, BinaryOp):
            return self._binary_op(node)
        return "error"

    def _binary_op(self, node: BinaryOp) -> str:
        left_type = self._expr(node.left)
        right_type = self._expr(node.right)
        if "error" in (left_type, right_type):
            return "error"

        if node.op in ARITHMETIC_OPS:
            if left_type != "int" or right_type != "int":
                self._error(
                    "type-mismatch",
                    f"'{node.op}' requires int operands, got {left_type} and {right_type}",
                    node.line,
                )
                return "error"
            return "int"

        if node.op in COMPARISON_OPS:
            if left_type != right_type:
                self._error(
                    "type-mismatch",
                    f"'{node.op}' requires operands of the same type, got {left_type} and {right_type}",
                    node.line,
                )
                return "error"
            return "bool"

        if node.op in LOGICAL_OPS:
            if left_type != "bool" or right_type != "bool":
                self._error(
                    "type-mismatch",
                    f"'{node.op}' requires bool operands, got {left_type} and {right_type}",
                    node.line,
                )
                return "error"
            return "bool"

        return "error"
