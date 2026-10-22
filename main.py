"""
main.py
-------
Demo entry point for the Phase 2 prototype.

Usage:
    python main.py tests/programs/valid_basic.mcl
    python main.py tests/programs/malformed_multi_error.mcl
    python main.py tests/programs/semantic_error.mcl
    python main.py broken.mcl --repair --method rules               (Phase 3, no AI)
    python main.py broken.mcl --repair --method ollama --shots 3   (Phase 3, local LLM)

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


def run(path: str, do_repair=False, method="rules", model_name=None, shots=3, adapter=None):
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

    # -- self-validating repair (Phase 3, only with --repair) -----------
    if do_repair:
        if not parser.errors and not sem_errors:
            print("\n=== Suggested Repair ===\n  (skipped — the program has no errors)")
        else:
            from mcl_repair import make_model, repair
            model = make_model(method, model_name, shots, adapter=adapter)
            res = repair(source, model)
            print(f"\n=== Suggested Repair ({method}: {res.status}, {res.attempts} attempt(s)) ===")
            print(res.repaired)
            if res.status == "verified":
                print("\n  verified: the suggested program passes the lexer, parser and semantic analyzer")
            else:
                print("\n  UNVERIFIED: the suggestion still has errors; do not trust it")

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="MCL compiler front end demo")
    ap.add_argument("path", help="the .mcl file to compile")
    ap.add_argument("--repair", action="store_true", help="suggest and verify a fix for any errors")
    ap.add_argument("--method", choices=["rules", "ollama", "hybrid", "hf"], default="rules",
                    help="how to propose the fix (default: rules, no AI)")
    ap.add_argument("--model", default=None, help="Ollama model name (default qwen2.5:3b)")
    ap.add_argument("--shots", type=int, default=3, help="worked examples for the LLM (0 = zero-shot)")
    ap.add_argument("--adapter", default=None, help="LoRA adapter folder (method hf only)")
    a = ap.parse_args()
    run(a.path, do_repair=a.repair, method=a.method, model_name=a.model, shots=a.shots, adapter=a.adapter)
