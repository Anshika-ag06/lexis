import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcl_lexer import Lexer
from mcl_parser import Parser
from mcl_irgen import IRGenerator


def generate(src):
    tokens = Lexer(src).tokenize()
    ast = Parser(tokens, src).parse_program()
    return IRGenerator().generate(ast)


def test_decl_emits_simple_assignment():
    code = generate("int x = 5;")
    assert len(code) == 1
    assert code[0].op == "="
    assert code[0].result == "x"
    assert code[0].arg1 == "5"


def test_binary_expression_uses_a_temporary():
    code = generate("int x = 1 + 2;")
    # one instruction to compute the temp, one to assign it to x
    assert len(code) == 2
    add_instr, assign_instr = code
    assert add_instr.op == "+"
    assert add_instr.result == "t1"
    assert assign_instr.result == "x"
    assert assign_instr.arg1 == "t1"


def test_if_without_else_generates_one_label():
    code = generate("int x = 1;\nif (x < 2) {\n    print(x);\n}")
    labels = [q for q in code if q.op == "label"]
    assert len(labels) == 1
    branches = [q for q in code if q.op == "if_false_goto"]
    assert len(branches) == 1
    assert branches[0].result == labels[0].result


def test_if_with_else_generates_two_labels_and_a_goto():
    code = generate("int x = 1;\nif (x < 2) {\n    print(x);\n} else {\n    print(x);\n}")
    labels = [q for q in code if q.op == "label"]
    gotos = [q for q in code if q.op == "goto"]
    assert len(labels) == 2
    assert len(gotos) == 1


def test_while_loops_back_to_start_label():
    code = generate("int x = 1;\nwhile (x < 2) {\n    x = x + 1;\n}")
    labels = [q for q in code if q.op == "label"]
    gotos = [q for q in code if q.op == "goto"]
    assert len(labels) == 2
    # the loop-back goto must target the *first* label (the loop start)
    assert gotos[0].result == labels[0].result


def test_print_emits_print_instruction():
    code = generate("int x = 1;\nprint(x);")
    print_instrs = [q for q in code if q.op == "print"]
    assert len(print_instrs) == 1
    assert print_instrs[0].arg1 == "x"
