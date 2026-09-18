"""
mcl_ast.py
----------
AST node definitions for MCL, built with lightweight Python dataclasses.
Only successfully parsed regions produce nodes; the parser skips node
construction for statements it had to recover from.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Node:
    line: int = field(default=0, repr=False)


@dataclass
class Program(Node):
    statements: List[Node] = field(default_factory=list)


@dataclass
class Decl(Node):
    var_type: str = ""      # "int" | "bool"
    name: str = ""
    expr: Optional[Node] = None


@dataclass
class Assign(Node):
    name: str = ""
    expr: Optional[Node] = None


@dataclass
class If(Node):
    cond: Optional[Node] = None
    then_block: List[Node] = field(default_factory=list)
    else_block: Optional[List[Node]] = None


@dataclass
class While(Node):
    cond: Optional[Node] = None
    body: List[Node] = field(default_factory=list)


@dataclass
class Print(Node):
    expr: Optional[Node] = None


@dataclass
class BinaryOp(Node):
    op: str = ""
    left: Optional[Node] = None
    right: Optional[Node] = None


@dataclass
class Literal(Node):
    value: object = None
    kind: str = ""  # "int" | "bool"


@dataclass
class Identifier(Node):
    name: str = ""


@dataclass
class ErrorNode(Node):
    """Placeholder inserted where a statement could not be parsed even
    after recovery, so the AST keeps a record of the gap without
    pretending real content was there."""
    note: str = "recovered-error"
