import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcl_lexer import Lexer, TokenType, LexicalError


def token_types(src):
    return [t.type for t in Lexer(src).tokenize()]


def test_keywords_and_identifiers():
    types = token_types("int x = 5;")
    assert types == [
        TokenType.INT, TokenType.IDENT, TokenType.ASSIGN,
        TokenType.NUMBER, TokenType.SEMI, TokenType.EOF,
    ]


def test_multi_char_operators_prefer_longest_match():
    types = token_types("x == y != z <= w >= v && u || t")
    assert TokenType.EQ in types
    assert TokenType.NEQ in types
    assert TokenType.LE in types
    assert TokenType.GE in types
    assert TokenType.AND in types
    assert TokenType.OR in types
    # single '=' must not have been consumed as part of '=='
    assert TokenType.ASSIGN not in types


def test_boolean_and_int_literals():
    types = token_types("bool flag = true;")
    assert types[:5] == [
        TokenType.BOOL, TokenType.IDENT, TokenType.ASSIGN,
        TokenType.TRUE, TokenType.SEMI,
    ]


def test_comments_are_skipped():
    types = token_types("int x = 1; // this is a comment\nint y = 2;")
    assert types.count(TokenType.INT) == 2


def test_line_and_column_tracking():
    tokens = Lexer("int x = 5;\nint y = 10;").tokenize()
    second_int = [t for t in tokens if t.type == TokenType.INT][1]
    assert second_int.line == 2
    assert second_int.column == 1


def test_illegal_character_raises_lexical_error():
    with pytest.raises(LexicalError):
        Lexer("int x = 5; print(x @ 1);").tokenize()


def test_malformed_numeric_literal_raises_lexical_error():
    with pytest.raises(LexicalError):
        Lexer("int y = 12abc;").tokenize()
