"""
mcl_parser.py
-------------
Recursive-descent parser for MCL that builds an AST for well-formed
regions and performs multi-error syntax recovery instead of halting
at the first mistake.

Recovery strategy (Phase 1, Section 9.2):
    * Phrase-level: for a small set of high-frequency mistakes (missing
      ';', unbalanced '(' ')') attempt a single-token insertion before
      falling back to panic-mode.
    * Panic-mode: on a rule mismatch inside a statement, discard tokens
      until the next ';', '{' or '}' is found, then resume parsing the
      next statement.

Every recovery action is captured as a SyntaxErrorRecord (see
mcl_errors.py) rather than a raw message string.
"""

from typing import List, Optional

from mcl_lexer import Token, TokenType
from mcl_errors import SyntaxErrorRecord
from mcl_ast import (
    Program, Decl, Assign, If, While, Print,
    BinaryOp, Literal, Identifier, ErrorNode, Node,
)

# Tokens that can legally start a new statement — used both to decide
# whether a missing ';' can be safely assumed, and as extra
# synchronization points for panic-mode.
STATEMENT_START = {
    TokenType.INT, TokenType.BOOL, TokenType.IF, TokenType.WHILE,
    TokenType.PRINT, TokenType.IDENT,
}

SYNC_TOKENS = {TokenType.SEMI, TokenType.LBRACE, TokenType.RBRACE, TokenType.EOF}

COMPARISON_OPS = {
    TokenType.PLUS, TokenType.MINUS, TokenType.EQ, TokenType.LT,
    TokenType.GT, TokenType.LE, TokenType.GE, TokenType.AND, TokenType.OR,
}


class Parser:
    def __init__(self, tokens: List[Token], source: str = ""):
        self.tokens = tokens
        self.pos = 0
        self.errors: List[SyntaxErrorRecord] = []
        self.source_lines = source.splitlines()

    # -- token stream helpers -------------------------------------------------
    def _peek(self, offset: int = 0) -> Token:
        idx = min(self.pos + offset, len(self.tokens) - 1)
        return self.tokens[idx]

    def _advance(self) -> Token:
        tok = self.tokens[self.pos]
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return tok

    def _check(self, ttype: TokenType) -> bool:
        return self._peek().type == ttype

    def _snippet(self, line: int) -> str:
        return self.source_lines[line - 1] if 0 < line <= len(self.source_lines) else ""

    def _record_error(self, expected: str, recovery_action: str, tok: Optional[Token] = None):
        tok = tok or self._peek()
        rec = SyntaxErrorRecord(
            expected_token=expected,
            actual_token=tok.lexeme if tok.type != TokenType.EOF else "<EOF>",
            line=tok.line,
            column=tok.column,
            recovery_action=recovery_action,
            snippet=self._snippet(tok.line),
        )
        self.errors.append(rec)
        return rec

    # -- expect() with phrase-level recovery built in -------------------------
    def _expect(self, ttype: TokenType, display: str) -> Optional[Token]:
        """Consume a token of type `ttype`. On mismatch, try a phrase-level
        fix (virtual insertion) before returning None to signal the caller
        should fall back to panic-mode."""
        if self._check(ttype):
            return self._advance()

        # Phrase-level: missing ';' — if the current token could start a
        # new statement, or closes a block, assume the ';' was omitted.
        if ttype == TokenType.SEMI and (
            self._peek().type in STATEMENT_START or self._peek().type in (TokenType.RBRACE, TokenType.EOF)
        ):
            self._record_error(display, "phrase-level: inserted missing ';'")
            return None  # caller treats this as "handled", statement ends here

        # Phrase-level: missing ')' — if we're stuck at '{' or ';' when a
        # ')' was expected, assume the ')' was omitted.
        if ttype == TokenType.RPAREN and self._peek().type in (TokenType.LBRACE, TokenType.SEMI):
            self._record_error(display, "phrase-level: inserted missing ')'")
            return None

        # No safe local repair — signal panic-mode is needed.
        self._record_error(display, "panic-mode: resynchronizing at next ';' or block delimiter")
        self._panic_mode()
        return None

    def _panic_mode(self):
        """Discard tokens until a synchronizing token is found.

        The offending token itself is always discarded first (even if it
        happens to already be a sync token, e.g. a stray unmatched '}')
        so panic-mode is guaranteed to make forward progress and cannot
        spin forever on a single bad token."""
        self._advance()
        while self._peek().type not in SYNC_TOKENS:
            self._advance()
        # Consume the ';' itself if that's what we landed on, so the
        # caller starts clean on the next statement.
        if self._check(TokenType.SEMI):
            self._advance()

    # -- grammar ---------------------------------------------------------------
    def parse_program(self) -> Program:
        prog = Program(line=1)
        while not self._check(TokenType.EOF):
            stmt = self._parse_statement()
            if stmt is not None:
                prog.statements.append(stmt)
        return prog

    def _parse_statement(self) -> Optional[Node]:
        tok = self._peek()

        if tok.type in (TokenType.INT, TokenType.BOOL):
            return self._parse_decl()
        if tok.type == TokenType.IDENT:
            return self._parse_assign()
        if tok.type == TokenType.IF:
            return self._parse_if()
        if tok.type == TokenType.WHILE:
            return self._parse_while()
        if tok.type == TokenType.PRINT:
            return self._parse_print()

        # Unknown start of statement -> record + panic-mode, return an
        # ErrorNode so the AST keeps a placeholder for the gap.
        self._record_error(
            "start of statement (decl/assign/if/while/print)",
            "panic-mode: resynchronizing at next ';' or block delimiter",
        )
        line = tok.line
        self._panic_mode()
        return ErrorNode(line=line)

    def _parse_decl(self) -> Node:
        type_tok = self._advance()  # 'int' | 'bool'
        line = type_tok.line
        name = None
        if self._check(TokenType.IDENT):
            name = self._advance().lexeme
        else:
            self._record_error("identifier", "panic-mode: resynchronizing at next ';' or block delimiter")
            self._panic_mode()
            return ErrorNode(line=line)

        self._expect(TokenType.ASSIGN, "'='")
        expr = self._parse_expr()
        self._expect(TokenType.SEMI, "';'")
        return Decl(line=line, var_type=type_tok.lexeme, name=name, expr=expr)

    def _parse_assign(self) -> Node:
        name_tok = self._advance()
        line = name_tok.line
        self._expect(TokenType.ASSIGN, "'='")
        expr = self._parse_expr()
        self._expect(TokenType.SEMI, "';'")
        return Assign(line=line, name=name_tok.lexeme, expr=expr)

    def _parse_if(self) -> Node:
        line = self._advance().line  # 'if'
        self._expect(TokenType.LPAREN, "'('")
        cond = self._parse_expr()
        self._expect(TokenType.RPAREN, "')'")
        then_block = self._parse_block()
        else_block = None
        if self._check(TokenType.ELSE):
            self._advance()
            else_block = self._parse_block()
        return If(line=line, cond=cond, then_block=then_block, else_block=else_block)

    def _parse_while(self) -> Node:
        line = self._advance().line  # 'while'
        self._expect(TokenType.LPAREN, "'('")
        cond = self._parse_expr()
        self._expect(TokenType.RPAREN, "')'")
        body = self._parse_block()
        return While(line=line, cond=cond, body=body)

    def _parse_print(self) -> Node:
        line = self._advance().line  # 'print'
        self._expect(TokenType.LPAREN, "'('")
        expr = self._parse_expr()
        self._expect(TokenType.RPAREN, "')'")
        self._expect(TokenType.SEMI, "';'")
        return Print(line=line, expr=expr)

    def _parse_block(self) -> List[Node]:
        stmts: List[Node] = []
        if not self._check(TokenType.LBRACE):
            self._record_error("'{'", "panic-mode: resynchronizing at next ';' or block delimiter")
            self._panic_mode()
            return stmts
        self._advance()  # '{'
        while not self._check(TokenType.RBRACE) and not self._check(TokenType.EOF):
            stmt = self._parse_statement()
            if stmt is not None:
                stmts.append(stmt)
        if self._check(TokenType.RBRACE):
            self._advance()
        else:
            self._record_error("'}'", "panic-mode: resynchronizing at next ';' or block delimiter")
            self._panic_mode()
        return stmts

    # expr ::= term { ("+"|"-"|"=="|"<"|">"|"&&"|"||") term }
    def _parse_expr(self) -> Optional[Node]:
        left = self._parse_term()
        while self._peek().type in COMPARISON_OPS:
            op_tok = self._advance()
            right = self._parse_term()
            left = BinaryOp(line=op_tok.line, op=op_tok.lexeme, left=left, right=right)
        return left

    # term ::= factor { ("*"|"/") factor }
    def _parse_term(self) -> Optional[Node]:
        left = self._parse_factor()
        while self._peek().type in (TokenType.STAR, TokenType.SLASH):
            op_tok = self._advance()
            right = self._parse_factor()
            left = BinaryOp(line=op_tok.line, op=op_tok.lexeme, left=left, right=right)
        return left

    # factor ::= IDENT | NUMBER | "true" | "false" | "(" expr ")"
    def _parse_factor(self) -> Optional[Node]:
        tok = self._peek()
        if tok.type == TokenType.IDENT:
            self._advance()
            return Identifier(line=tok.line, name=tok.lexeme)
        if tok.type == TokenType.NUMBER:
            self._advance()
            return Literal(line=tok.line, value=int(tok.lexeme), kind="int")
        if tok.type in (TokenType.TRUE, TokenType.FALSE):
            self._advance()
            return Literal(line=tok.line, value=(tok.type == TokenType.TRUE), kind="bool")
        if tok.type == TokenType.LPAREN:
            self._advance()
            expr = self._parse_expr()
            self._expect(TokenType.RPAREN, "')'")
            return expr

        self._record_error(
            "expression (identifier, number, true/false, or '(')",
            "panic-mode: resynchronizing at next ';' or block delimiter",
        )
        self._panic_mode()
        return ErrorNode(line=tok.line)
