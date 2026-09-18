import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcl_lexer import Lexer
from mcl_parser import Parser
from mcl_ast import Decl, Assign, If, While, Print, ErrorNode


def parse(src):
    tokens = Lexer(src).tokenize()
    parser = Parser(tokens, src)
    ast = parser.parse_program()
    return ast, parser.errors


def test_valid_program_produces_no_errors():
    src = """
    int x = 5;
    bool flag = true;
    if (x < 10) {
        print(x);
    } else {
        print(flag);
    }
    while (x < 10) {
        x = x + 1;
    }
    """
    ast, errors = parse(src)
    assert errors == []
    assert len(ast.statements) == 4
    assert isinstance(ast.statements[0], Decl)
    assert isinstance(ast.statements[1], Decl)
    assert isinstance(ast.statements[2], If)
    assert isinstance(ast.statements[3], While)


def test_expression_precedence():
    ast, errors = parse("int x = 1 + 2 * 3;")
    assert errors == []
    decl = ast.statements[0]
    # '+' should be the outermost node since '*' binds tighter
    assert decl.expr.op == "+"
    assert decl.expr.right.op == "*"


def test_missing_semicolon_is_phrase_level_recovered_and_parsing_continues():
    src = "int x = 5\nint y = 10;"
    ast, errors = parse(src)
    assert len(errors) == 1
    assert "phrase-level" in errors[0].recovery_action
    assert "';'" in errors[0].expected_token
    # both declarations still end up in the AST despite the missing ';'
    assert len(ast.statements) == 2
    assert isinstance(ast.statements[0], Decl)
    assert isinstance(ast.statements[1], Decl)


def test_missing_closing_paren_is_phrase_level_recovered():
    src = "if (x < 5 { print(x); }"
    ast, errors = parse(src)
    assert any("')'" in e.expected_token for e in errors)
    assert isinstance(ast.statements[0], If)


def test_multiple_independent_errors_recovered_in_one_pass():
    src = (
        "int x = 5\n"          # missing ';' (phrase-level)
        "int y = 10;\n"
        ") z = 1;\n"           # invalid statement start (panic-mode)
        "print(y);\n"
    )
    ast, errors = parse(src)
    # at least two distinct recovery events, and the parser did not stop
    # after the first error — later valid statements still parse.
    assert len(errors) >= 2
    prints = [s for s in ast.statements if isinstance(s, Print)]
    assert len(prints) == 1


def test_invalid_statement_start_triggers_panic_mode_and_error_node():
    ast, errors = parse(") x = 1;\nprint(x);")
    assert len(errors) == 1
    assert "panic-mode" in errors[0].recovery_action
    assert isinstance(ast.statements[0], ErrorNode)
    assert isinstance(ast.statements[1], Print)


def test_structured_error_object_fields():
    _, errors = parse("int x = 5\nint y = 10;")
    err = errors[0]
    d = err.to_dict()
    assert set(d.keys()) == {
        "expected_token", "actual_token", "line", "column",
        "recovery_action", "snippet",
    }
    # the missing ';' is detected at the token that follows it (start of
    # the next declaration), which lands on line 2
    assert d["line"] == 2
