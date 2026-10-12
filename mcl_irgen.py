"""
mcl_irgen.py
------------
Three-address code (TAC) generator for MCL (Phase 2, Section 10.2 -
Intermediate Code).

Walks the AST built by mcl_parser.Parser and emits a flat list of `Quad`
instructions using temporaries (t1, t2, ...) for intermediate expression
results and labels (L1, L2, ...) for control flow - the standard
three-address-code scheme used to bridge a compiler's front end
(lexer/parser/semantic analysis) and a back end (interpreter or codegen).

This stage assumes it is only ever handed an AST that came back with no
unresolved `ErrorNode`s (see `main.py`): generating code for a gap the
parser could not recover would only produce meaningless instructions.
"""

from dataclasses import dataclass
from typing import List, Optional

from mcl_ast import (
    Assign, BinaryOp, Decl, ErrorNode, Identifier, If, Literal, Node,
    Print, Program, While,
)


@dataclass
class Quad:
    """One three-address instruction: `result = arg1 op arg2`, or one of
    the control-flow / I-O special forms handled in __str__."""
    op: str
    arg1: Optional[str] = None
    arg2: Optional[str] = None
    result: Optional[str] = None

    def __str__(self):
        if self.op == "label":
            return f"{self.result}:"
        if self.op == "goto":
            return f"    goto {self.result}"
        if self.op == "if_false_goto":
            return f"    ifFalse {self.arg1} goto {self.result}"
        if self.op == "print":
            return f"    print {self.arg1}"
        if self.op == "=":
            return f"    {self.result} = {self.arg1}"
        return f"    {self.result} = {self.arg1} {self.op} {self.arg2}"


class IRGenerator:
    def __init__(self):
        self.code: List[Quad] = []
        self._temp_count = 0
        self._label_count = 0

    def _new_temp(self) -> str:
        self._temp_count += 1
        return f"t{self._temp_count}"

    def _new_label(self) -> str:
        self._label_count += 1
        return f"L{self._label_count}"

    def _emit(self, op, arg1=None, arg2=None, result=None) -> None:
        self.code.append(Quad(op, arg1, arg2, result))

    # -- entry point -------------------------------------------------------
    def generate(self, program: Program) -> List[Quad]:
        for stmt in program.statements:
            self._stmt(stmt)
        return self.code

    # -- statements ----------------------------------------------------------
    def _stmt(self, node: Optional[Node]) -> None:
        if node is None or isinstance(node, ErrorNode):
            return
        if isinstance(node, Decl):
            val = self._expr(node.expr)
            self._emit("=", arg1=val, result=node.name)
        elif isinstance(node, Assign):
            val = self._expr(node.expr)
            self._emit("=", arg1=val, result=node.name)
        elif isinstance(node, If):
            self._gen_if(node)
        elif isinstance(node, While):
            self._gen_while(node)
        elif isinstance(node, Print):
            val = self._expr(node.expr)
            self._emit("print", arg1=val)

    def _gen_if(self, node: If) -> None:
        cond = self._expr(node.cond)
        else_label = self._new_label()
        end_label = self._new_label() if node.else_block is not None else else_label
        self._emit("if_false_goto", arg1=cond, result=else_label)
        for s in node.then_block:
            self._stmt(s)
        if node.else_block is not None:
            self._emit("goto", result=end_label)
            self._emit("label", result=else_label)
            for s in node.else_block:
                self._stmt(s)
        self._emit("label", result=end_label)

    def _gen_while(self, node: While) -> None:
        start_label = self._new_label()
        end_label = self._new_label()
        self._emit("label", result=start_label)
        cond = self._expr(node.cond)
        self._emit("if_false_goto", arg1=cond, result=end_label)
        for s in node.body:
            self._stmt(s)
        self._emit("goto", result=start_label)
        self._emit("label", result=end_label)

    # -- expressions: return the name/temp holding the value -----------------
    def _expr(self, node: Optional[Node]) -> str:
        if node is None or isinstance(node, ErrorNode):
            return "<error>"
        if isinstance(node, Literal):
            if node.value is True:
                return "true"
            if node.value is False:
                return "false"
            return str(node.value)
        if isinstance(node, Identifier):
            return node.name
        if isinstance(node, BinaryOp):
            left = self._expr(node.left)
            right = self._expr(node.right)
            temp = self._new_temp()
            self._emit(node.op, arg1=left, arg2=right, result=temp)
            return temp
        return "<error>"
