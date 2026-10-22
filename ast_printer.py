"""
ast_printer.py
--------------
Minimal indented pretty-printer for MCL AST nodes — used only to make
the demo output readable, not part of the required compiler pipeline.
"""

from mcl_ast import Program, Decl, Assign, If, While, Print, BinaryOp, Literal, Identifier, ErrorNode


def print_ast(node, indent=0):
    pad = "  " * indent
    if isinstance(node, Program):
        print(f"{pad}Program")
        for s in node.statements:
            print_ast(s, indent + 1)
    elif isinstance(node, Decl):
        print(f"{pad}Decl({node.var_type} {node.name})  [line {node.line}]")
        print_ast(node.expr, indent + 1)
    elif isinstance(node, Assign):
        print(f"{pad}Assign({node.name})  [line {node.line}]")
        print_ast(node.expr, indent + 1)
    elif isinstance(node, If):
        print(f"{pad}If  [line {node.line}]")
        print(f"{pad}  cond:")
        print_ast(node.cond, indent + 2)
        print(f"{pad}  then:")
        for s in node.then_block:
            print_ast(s, indent + 2)
        if node.else_block is not None:
            print(f"{pad}  else:")
            for s in node.else_block:
                print_ast(s, indent + 2)
    elif isinstance(node, While):
        print(f"{pad}While  [line {node.line}]")
        print(f"{pad}  cond:")
        print_ast(node.cond, indent + 2)
        print(f"{pad}  body:")
        for s in node.body:
            print_ast(s, indent + 2)
    elif isinstance(node, Print):
        print(f"{pad}Print  [line {node.line}]")
        print_ast(node.expr, indent + 1)
    elif isinstance(node, BinaryOp):
        print(f"{pad}BinaryOp({node.op})  [line {node.line}]")
        print_ast(node.left, indent + 1)
        print_ast(node.right, indent + 1)
    elif isinstance(node, Literal):
        print(f"{pad}Literal({node.value})  [line {node.line}]")
    elif isinstance(node, Identifier):
        print(f"{pad}Identifier({node.name})  [line {node.line}]")
    elif isinstance(node, ErrorNode):
        print(f"{pad}<ErrorNode: {node.note}>  [line {node.line}]")
    elif node is None:
        print(f"{pad}<None>")
    else:
        print(f"{pad}{node!r}")
