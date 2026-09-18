"""
main.py
-------
Demo entry point for the Phase 1 prototype.

Usage:
    python main.py tests/programs/valid_basic.mcl
    python main.py tests/programs/malformed_multi_error.mcl

Runs: lexer -> parser (with panic-mode / phrase-level recovery) and
prints the token stream, the resulting AST, and every structured
error/recovery record collected during parsing.

Note: the LLM diagnostic layer and the self-validating fix loop
(Sections 9.3 / 9.4 of the Phase 1 report) are NOT part of this
prototype — this file demonstrates only the lexer + parser + error
recovery, as required for the Review 1 deliverable.
"""

import sys

from mcl_lexer import Lexer, LexicalError
from mcl_parser import Parser
from ast_printer import print_ast


def run(path: str):
    with open(path, "r") as f:
        source = f.read()

    print(f"=== Source: {path} ===\n{source}\n")

    try:
        tokens = Lexer(source).tokenize()
    except LexicalError as e:
        print(f"LEXICAL ERROR: {e.message} at line {e.line}, column {e.column}")
        print(f"    {e.snippet}")
        return

    print("=== Tokens ===")
    for tok in tokens:
        print(" ", tok)

    parser = Parser(tokens, source)
    ast = parser.parse_program()

    print("\n=== AST ===")
    print_ast(ast)

    print(f"\n=== Recovered Errors ({len(parser.errors)}) ===")
    if not parser.errors:
        print("  (none — program parsed cleanly)")
    for i, err in enumerate(parser.errors, 1):
        print(f"\n  Error #{i}")
        for line in str(err).splitlines():
            print(f"    {line}")

    print(f"\nSummary: {len(parser.errors)} syntax error(s) recovered in a single pass "
          f"({len(ast.statements)} top-level statement slots produced).")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python main.py <path-to-.mcl-file>")
        sys.exit(1)
    run(sys.argv[1])
