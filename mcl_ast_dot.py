"""
mcl_ast_dot.py
--------------
AST visualization for MCL (Phase 2, Section 10.2 - AST construction,
traversal, and visualization).

`ast_printer.py` already gives a textual, indented traversal for the
terminal. This module walks the same tree and emits a Graphviz DOT
file instead, so the AST can be rendered as an actual tree diagram
(`dot -Tpng tree.dot -o tree.png`) for the review slides / report.
"""

from itertools import count

from mcl_ast import (
    Assign, BinaryOp, Decl, ErrorNode, Identifier, If, Literal, Print,
    Program, While,
)

_id_counter = count()


def _label(node) -> str:
    if isinstance(node, Program):
        return "Program"
    if isinstance(node, Decl):
        return f"Decl\\n{node.var_type} {node.name}"
    if isinstance(node, Assign):
        return f"Assign\\n{node.name}"
    if isinstance(node, If):
        return "If"
    if isinstance(node, While):
        return "While"
    if isinstance(node, Print):
        return "Print"
    if isinstance(node, BinaryOp):
        return f"BinaryOp\\n{node.op}"
    if isinstance(node, Literal):
        return f"Literal\\n{node.value}"
    if isinstance(node, Identifier):
        return f"Identifier\\n{node.name}"
    if isinstance(node, ErrorNode):
        return "ErrorNode"
    return node.__class__.__name__


def _add_node(lines, node, parent_id=None):
    if node is None:
        return
    my_id = f"n{next(_id_counter)}"
    shape = "box" if isinstance(node, ErrorNode) else "ellipse"
    lines.append(f'  {my_id} [label="{_label(node)}", shape={shape}];')
    if parent_id is not None:
        lines.append(f"  {parent_id} -> {my_id};")

    if isinstance(node, Program):
        for s in node.statements:
            _add_node(lines, s, my_id)
    elif isinstance(node, Decl):
        _add_node(lines, node.expr, my_id)
    elif isinstance(node, Assign):
        _add_node(lines, node.expr, my_id)
    elif isinstance(node, If):
        _add_node(lines, node.cond, my_id)
        for s in node.then_block:
            _add_node(lines, s, my_id)
        if node.else_block is not None:
            for s in node.else_block:
                _add_node(lines, s, my_id)
    elif isinstance(node, While):
        _add_node(lines, node.cond, my_id)
        for s in node.body:
            _add_node(lines, s, my_id)
    elif isinstance(node, Print):
        _add_node(lines, node.expr, my_id)
    elif isinstance(node, BinaryOp):
        _add_node(lines, node.left, my_id)
        _add_node(lines, node.right, my_id)


def ast_to_dot(program: Program) -> str:
    """Render `program` as a Graphviz DOT source string."""
    lines = ["digraph AST {", '  node [fontname="Helvetica", fontsize=10];']
    _add_node(lines, program)
    lines.append("}")
    return "\n".join(lines)
