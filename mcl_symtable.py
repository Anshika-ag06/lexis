"""
mcl_symtable.py
----------------
Symbol table for MCL (Phase 2, Section 10.2 - Symbol Table).

Implemented as a stack of scopes so nested blocks (if/while bodies) get
their own lexical scope while still being able to see enclosing
declarations. This mirrors the block structure the parser already
recognizes via `Parser._parse_block` - every `{ ... }` the parser sees
becomes one `enter_scope()` / `exit_scope()` pair here.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Symbol:
    name: str
    type: str          # "int" | "bool"
    line: int           # line of declaration
    scope_level: int


class SymbolTable:
    def __init__(self):
        # scopes[0] is the global scope; each nested block pushes a new dict.
        self.scopes: List[Dict[str, Symbol]] = [{}]

    @property
    def level(self) -> int:
        return len(self.scopes) - 1

    def enter_scope(self) -> None:
        self.scopes.append({})

    def exit_scope(self) -> None:
        if len(self.scopes) > 1:
            self.scopes.pop()

    def declare(self, name: str, type_: str, line: int) -> Optional[Symbol]:
        """Insert a new symbol in the *current* (innermost) scope.

        Returns the pre-existing Symbol if `name` is already declared in
        this exact scope (a redeclaration the caller should report), or
        None on a successful, fresh declaration.
        """
        current = self.scopes[-1]
        if name in current:
            return current[name]
        current[name] = Symbol(name=name, type=type_, line=line, scope_level=self.level)
        return None

    def lookup(self, name: str) -> Optional[Symbol]:
        """Search from the innermost scope outward to the global scope."""
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return None

    def all_symbols(self) -> List[Symbol]:
        """Flatten every symbol across every currently-open scope - used
        for printing a symbol-table dump in the demo output."""
        out: List[Symbol] = []
        for scope in self.scopes:
            out.extend(scope.values())
        return out
