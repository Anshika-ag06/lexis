import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcl_lexer import Lexer
from mcl_parser import Parser
from mcl_semantic import SemanticAnalyzer


def analyze(src):
    tokens = Lexer(src).tokenize()
    ast = Parser(tokens, src).parse_program()
    analyzer = SemanticAnalyzer(src)
    errors = analyzer.analyze(ast)
    return errors, analyzer.symtab


def test_valid_program_has_no_semantic_errors():
    src = """
    int x = 5;
    bool flag = true;
    if (x < 10) {
        print(x);
    }
    while (flag) {
        x = x + 1;
    }
    """
    errors, _ = analyze(src)
    assert errors == []


def test_redeclaration_in_same_scope_is_reported():
    errors, _ = analyze("int x = 5;\nint x = 10;")
    assert len(errors) == 1
    assert errors[0].kind == "redeclaration"


def test_shadowing_in_nested_scope_is_allowed():
    src = "int x = 5;\nif (x < 10) {\n    int x = 1;\n    print(x);\n}"
    errors, _ = analyze(src)
    assert errors == []


def test_undeclared_identifier_is_reported():
    errors, _ = analyze("x = 5;")
    assert len(errors) == 1
    assert errors[0].kind == "undeclared"


def test_type_mismatch_on_declaration_is_reported():
    errors, _ = analyze("bool flag = 5;")
    assert len(errors) == 1
    assert errors[0].kind == "type-mismatch"


def test_type_mismatch_on_assignment_is_reported():
    errors, _ = analyze("int x = 5;\nx = true;")
    assert len(errors) == 1
    assert errors[0].kind == "type-mismatch"


def test_if_condition_must_be_bool():
    errors, _ = analyze("int x = 5;\nif (x) {\n    print(x);\n}")
    assert any(e.kind == "type-mismatch" for e in errors)


def test_arithmetic_requires_int_operands():
    errors, _ = analyze("bool a = true;\nint x = a + 1;")
    assert any(e.kind == "type-mismatch" for e in errors)


def test_undeclared_variable_does_not_cascade():
    # 'y' is undeclared, but using it later shouldn't produce a second,
    # misleading type-mismatch error on top of the one undeclared error.
    errors, _ = analyze("int x = y + 1;")
    assert len(errors) == 1
    assert errors[0].kind == "undeclared"


def test_symbol_table_populated_after_analysis():
    _, symtab = analyze("int x = 5;\nbool flag = true;")
    names = {s.name for s in symtab.all_symbols()}
    assert names == {"x", "flag"}
