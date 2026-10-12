"""
main.py
-------
Demo entry point for the Phase 2 prototype.

Usage:
    python main.py tests/programs/valid_basic.mcl
    python main.py tests/programs/malformed_multi_error.mcl
    python main.py tests/programs/semantic_error.mcl

Runs the full front-end pipeline built so far:
    lexer -> parser (panic-mode / phrase-level recovery)
          -> semantic analyzer (symbol table, scope/type/declaration checks)
          -> three-address-code generator

and prints the token stream, the AST, the symbol table, every recovered
syntax error, every semantic error, and (when the program is free of
both) the generated intermediate code.

Note: the LoRA fine-tuned repair model and the self-validating fix loop
(Sections 9.4 / 9.5 of the Phase 1 report) are Phase 3 work and are not
part of this prototype. `mcl_corruption.py` is the Phase 2 groundwork
for that layer: it mechanically generates the labeled synthetic dataset
the fine-tuning step will eventually train on.
"""

import sys

from mcl_lexer import Lexer, LexicalError
from mcl_parser import Parser
from mcl_semantic import SemanticAnalyzer
from mcl_irgen import IRGenerator
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

    print(f"\n=== Recovered Syntax Errors ({len(parser.errors)}) ===")
    if not parser.errors:
        print("  (none — program parsed cleanly)")
    for i, err in enumerate(parser.errors, 1):
        print(f"\n  Error #{i}")
        for line in str(err).splitlines():
            print(f"    {line}")

    # -- semantic analysis (Phase 2) -----------------------------------
    analyzer = SemanticAnalyzer(source)
    sem_errors = analyzer.analyze(ast)

    print(f"\n=== Symbol Table ({len(analyzer.symtab.all_symbols())} symbol(s)) ===")
    for sym in analyzer.symtab.all_symbols():
        print(f"  {sym.name:<10} type={sym.type:<5} declared at line {sym.line} (scope {sym.scope_level})")

    print(f"\n=== Semantic Errors ({len(sem_errors)}) ===")
    if not sem_errors:
        print("  (none — program is semantically valid)")
    for i, err in enumerate(sem_errors, 1):
        print(f"\n  Error #{i}")
        for line in str(err).splitlines():
            print(f"    {line}")

    # -- intermediate code generation (Phase 2) -------------------------
    if not parser.errors and not sem_errors:
        irgen = IRGenerator()
        code = irgen.generate(ast)
        print(f"\n=== Three-Address Code ({len(code)} instruction(s)) ===")
        for quad in code:
            print(str(quad))
    else:
        print("\n=== Three-Address Code ===")
        print("  (skipped — fix the syntax/semantic errors above first)")

    print(f"\nSummary: {len(parser.errors)} syntax error(s) and {len(sem_errors)} "
          f"semantic error(s) found ({len(ast.statements)} top-level statement slots produced).")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python main.py <path-to-.mcl-file>")
        sys.exit(1)
    run(sys.argv[1])
