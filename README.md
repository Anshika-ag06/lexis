# Lexis: Compiler with Intelligent Syntax Error Recovery and a Self-Validating Repair Layer

BCSE307P Compiler Design Laboratory, final project (Review 3).

Lexis is a compiler front end for **MCL (Mini Compiler Language)**. It finds every
independent syntax error in a program in a single pass, records each one as a structured
object, proposes a repair for each, and then **verifies the repair by running the parser
again**. A fix is only called *verified* if the patched program parses with zero errors.

> The model or rule proposes. The compiler alone decides whether a fix is correct.

## Scope

### Compiler front end
- Hand-written **lexical analyzer** (`mcl_lexer.py`): keywords, identifiers, integer and
  boolean literals, operators, delimiters, `//` comments, lexical errors (illegal characters,
  malformed numbers such as `12abc`).
- Hand-written **recursive-descent parser** (`mcl_parser.py`) for declarations, assignment,
  `if` / `else`, `while`, `print`, and expressions with correct precedence.
- **AST** (`mcl_ast.py`) with an `ErrorNode` placeholder for gaps the parser could not recover.
- **Multi-error recovery**: phrase-level insertion for a missing `;` and `)`, panic-mode
  resynchronization at `;`, `{`, `}` or EOF for everything else.
- **Structured errors** (`mcl_errors.py`): every recovery event is a `SyntaxErrorRecord`
  (`expected_token`, `actual_token`, `line`, `column`, `recovery_action`, `snippet`).
- Symbol table and semantic analysis, three-address code generation, Graphviz DOT export of
  the AST.

### Repair layer
- **Corruption engine** that breaks valid MCL programs in one controlled, reversible way,
  so the correct fix is known exactly and labelled data comes for free.
- Four repair strategies behind one interface:
  rules, zero-shot LLM, few-shot LLM, and a hybrid (rules first, LLM as fallback).
  LLM strategies use `qwen2.5:3b` running locally through Ollama.
- **Self-validating fix loop**: apply the patch, re-lex and re-parse, label it
  `VERIFIED` or `UNVERIFIED`.
- **Evaluation** on 100 test examples with two metrics: verified-fix rate (patched program
  parses) and exact-match rate (patched program equals the original).

## Results (100 test examples)

| Strategy | Verified | Exact match |
|---|---|---|
| Hybrid (rules + LLM fallback) | 99% | 93% |
| Rules | 97% | 91% |
| Few-shot LLM | 85% | 70% |
| Zero-shot LLM | 75% | 56% |

Verified does not imply exact: a model often produces a program that parses but is not what
the programmer originally wrote. That gap is why every fix is re-parsed and why exact match
is reported separately.

## Design decision: LoRA fine-tuning

The original plan fine-tuned a small code model (Qwen2.5-Coder-0.5B-Instruct) with LoRA on the
generated dataset. The training run could not be completed on Google Colab, so the project
used its planned fallback: a pretrained model used zero-shot, few-shot and inside the hybrid.
The verification loop, which is the core contribution, is unaffected. LoRA fine-tuning is
listed under the roadmap as future work.

## Project layout

```
lexis/
├── mcl_lexer.py          # Tokenizer + LexicalError
├── mcl_ast.py            # AST node dataclasses
├── mcl_errors.py         # SyntaxErrorRecord (structured diagnostic object)
├── mcl_parser.py         # Recursive-descent parser + phrase-level / panic-mode recovery
├── ast_printer.py        # Indented AST pretty-printer (demo only)
├── main.py               # CLI driver: lexer + parser on a .mcl file
├── corruption_engine.py  # Phase 2: controlled, reversible program corruption
├── dataset_builder.py    # Phase 2: builds labelled (broken, correct) pairs
├── validate_fix.py       # Phase 2: re-parse validation (VERIFIED / UNVERIFIED)
├── ...                   # symbol table, semantic analysis, TAC, repair strategies,
│                         # evaluation harness (see CODE_EXPLAINED.md)
├── tests/
│   ├── test_lexer.py
│   ├── test_parser.py
│   └── programs/
│       ├── valid_basic.mcl            # clean program, no errors
│       ├── malformed_multi_error.mcl  # 4 independent errors recovered in one pass
│       └── lexical_error.mcl          # malformed literal + illegal character
├── requirements.txt
├── README.md             # this file
├── CODE_EXPLAINED.md     # module-by-module walkthrough
└── HOW_TO_RUN.md         # commands and expected output
```

## Quick start

```bash
python3 main.py tests/programs/valid_basic.mcl            # clean program
python3 main.py tests/programs/malformed_multi_error.mcl  # 4 errors, one pass
python3 main.py tests/programs/lexical_error.mcl          # fatal lexical error
pytest tests/ -v                                          # unit tests
```

Requires Python 3.9+. The compiler itself has no dependencies; `pytest` is needed for tests,
and Ollama with `qwen2.5:3b` is needed only for the LLM repair strategies. See
`HOW_TO_RUN.md` for details.

## Mapping to compiler concepts

| Concept | Where |
|---|---|
| Lexical analysis | `mcl_lexer.py` |
| Context-free grammar, top-down parsing, precedence | `mcl_parser.py` (`expr` / `term` / `factor`) |
| Syntax tree | `mcl_ast.py`, `ast_printer.py`, DOT export |
| Syntax error recovery | `Parser._expect()` (phrase-level), `Parser._panic_mode()` |
| Symbol table, semantic analysis | Phase 2 modules |
| Intermediate code | Three-address code module |
| Verification of repairs | `validate_fix.py` and the fix loop |

## Known limitations

- Lexical errors are fatal: the lexer stops at the first illegal character or malformed
  literal. Recovering from them is a separate problem and is left as future work.
- `COMPARISON_OPS` in `mcl_parser.py` does not yet include `!=` (`NEQ`), and unary `!` is
  tokenized but not parsed. Adding `TokenType.NEQ` to `COMPARISON_OPS` fixes the first.
- Panic-mode can swallow a second nearby error into the same resynchronization jump
  (in `malformed_multi_error.mcl` the stray `)` is consumed together with the stray `}`).
- Verified means "parses", not "behaves the same". The rule score is partly by construction
  because the rules target the error classes the corruption engine generates.
- The 100-example test set is small and no confidence intervals were computed.

## Roadmap

| Status | Item |
|---|---|
| Done (Phase 1) | Lexer, parser, AST, dual recovery, structured errors |
| Done (Phase 2) | Corruption engine, dataset, symbol table, semantic checks, three-address code, fix loop |
| Done (Phase 3) | Rules / zero-shot / few-shot / hybrid repair, evaluation on 100 examples, final testing |
| Future | Complete LoRA fine-tuning of Qwen2.5-Coder-0.5B-Instruct (or CodeT5+) on a GPU and compare with the base model |
| Future | More language features (functions, arrays, strings, `for`) and real target code generation |
| Future | Test-based verification so "verified" implies equivalent behavior; evaluation on real student errors |
