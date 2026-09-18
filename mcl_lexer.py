"""
Lexical analyzer for MCL (Mini Compiler Language).

Recognizes:
    Keywords    : if else while print int bool true false
    Identifiers : [a-zA-Z_][a-zA-Z0-9_]*
    Literals    : integer literals (123), boolean literals (true/false)
    Operators   : + - * / = == != < > <= >= && || !
    Delimiters  : ( ) { } ;

Emits a LexError (via LexicalError exception) for illegal characters or
malformed literals, but is designed to be driven token-by-token so the
parser (and its recovery engine) stays in control of the overall pipeline.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional


class TokenType(Enum):
    # Keywords
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    PRINT = auto()
    INT = auto()
    BOOL = auto()
    TRUE = auto()
    FALSE = auto()

    IDENT = auto()
    NUMBER = auto()

    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    ASSIGN = auto()      # =
    EQ = auto()           # ==
    NEQ = auto()          # !=
    LT = auto()
    GT = auto()
    LE = auto()
    GE = auto()
    AND = auto()          # &&
    OR = auto()           # ||
    NOT = auto()          # !

    # Delimiters
    LPAREN = auto()
    RPAREN = auto()
    LBRACE = auto()
    RBRACE = auto()
    SEMI = auto()

    EOF = auto()


KEYWORDS = {
    "if": TokenType.IF,
    "else": TokenType.ELSE,
    "while": TokenType.WHILE,
    "print": TokenType.PRINT,
    "int": TokenType.INT,
    "bool": TokenType.BOOL,
    "true": TokenType.TRUE,
    "false": TokenType.FALSE,
}

SYMBOLS = [
    ("==", TokenType.EQ),
    ("!=", TokenType.NEQ),
    ("<=", TokenType.LE),
    (">=", TokenType.GE),
    ("&&", TokenType.AND),
    ("||", TokenType.OR),
    ("+", TokenType.PLUS),
    ("-", TokenType.MINUS),
    ("*", TokenType.STAR),
    ("/", TokenType.SLASH),
    ("=", TokenType.ASSIGN),
    ("<", TokenType.LT),
    (">", TokenType.GT),
    ("!", TokenType.NOT),
    ("(", TokenType.LPAREN),
    (")", TokenType.RPAREN),
    ("{", TokenType.LBRACE),
    ("}", TokenType.RBRACE),
    (";", TokenType.SEMI),
]


@dataclass
class Token:
    type: TokenType
    lexeme: str
    line: int
    column: int

    def __repr__(self):
        return f"Token({self.type.name}, {self.lexeme!r}, {self.line}:{self.column})"


class LexicalError(Exception):
    """Raised for illegal characters or malformed literals."""
    def __init__(self, message: str, line: int, column: int, snippet: str):
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column
        self.snippet = snippet


class Lexer:
    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.col = 1

    def _peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        return self.source[idx] if idx < len(self.source) else ""

    def _advance(self) -> str:
        ch = self.source[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _line_snippet(self, line_no: int) -> str:
        lines = self.source.splitlines()
        return lines[line_no - 1] if 0 < line_no <= len(lines) else ""

    def _skip_whitespace_and_comments(self):
        while self.pos < len(self.source):
            ch = self._peek()
            if ch in " \t\r\n":
                self._advance()
            elif ch == "/" and self._peek(1) == "/":
                while self.pos < len(self.source) and self._peek() != "\n":
                    self._advance()
            else:
                break

    def tokenize(self) -> List[Token]:
        """Tokenize the entire source. Raises LexicalError on the first
        illegal character (the parser layer is where *syntax* recovery
        happens; lexical errors are treated as fatal for simplicity)."""
        tokens: List[Token] = []
        while True:
            tok = self.next_token()
            tokens.append(tok)
            if tok.type == TokenType.EOF:
                break
        return tokens

    def next_token(self) -> Token:
        self._skip_whitespace_and_comments()

        if self.pos >= len(self.source):
            return Token(TokenType.EOF, "", self.line, self.col)

        start_line, start_col = self.line, self.col
        ch = self._peek()

        # Identifiers / keywords
        if ch.isalpha() or ch == "_":
            start = self.pos
            while self._peek().isalnum() or self._peek() == "_":
                self._advance()
            text = self.source[start:self.pos]
            ttype = KEYWORDS.get(text, TokenType.IDENT)
            return Token(ttype, text, start_line, start_col)

        # Number literals
        if ch.isdigit():
            start = self.pos
            while self._peek().isdigit():
                self._advance()
            # malformed literal: digits directly followed by letters, e.g. 12abc
            if self._peek().isalpha() or self._peek() == "_":
                while self._peek().isalnum() or self._peek() == "_":
                    self._advance()
                bad = self.source[start:self.pos]
                raise LexicalError(
                    f"Malformed numeric literal '{bad}'",
                    start_line, start_col, self._line_snippet(start_line),
                )
            return Token(TokenType.NUMBER, self.source[start:self.pos], start_line, start_col)

        # Operators / delimiters (longest match first)
        for sym, ttype in SYMBOLS:
            if self.source.startswith(sym, self.pos):
                for _ in sym:
                    self._advance()
                return Token(ttype, sym, start_line, start_col)

        # Illegal character
        bad_char = self._advance()
        raise LexicalError(
            f"Illegal character '{bad_char}'",
            start_line, start_col, self._line_snippet(start_line),
        )
