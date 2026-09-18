# MCL Compiler — Phase 1 Initial Prototype

BCSE307P Compiler Design Laboratory — Review 1 deliverable for:
**"Compiler with Intelligent Syntax Error Recovery and a Fine-Tuned, Self-Validating Repair Model"**

> Project title and AI-layer design were revised after Phase 1's initial proposal.
> The AI component is no longer a general-purpose LLM API call — it is a small,
> already-pretrained code model, adapted with **LoRA (Low-Rank Adaptation)** on a
> dataset this project generates itself (see **Roadmap** below). The code in this
> repository — the lexer, parser, AST, and dual-strategy error recovery — is
> unaffected by that revision and is complete and tested as described here.

## What this prototype covers (Section 13 of the Phase 1 report)

- Hand-written **lexical analyzer** (`mcl_lexer.py`) for MCL: keywords, identifiers,
  integer/boolean literals, all operators/delimiters, comment skipping, and
  lexical error detection (illegal characters, malformed numeric literals).
- Hand-written **recursive-descent parser** (`mcl_parser.py`) implementing the
  full grammar from the report (decl/assign/if/while/print, expressions with
  correct `+ -` / `* /` precedence).
- **AST construction** (`mcl_ast.py`) for successfully parsed regions.
- **Multi-error syntax recovery**:
  - *Phrase-level*: single-token virtual insertion for the two highest-frequency
    mistakes — a missing `;` and a missing `)` — so a trivial slip doesn't
    trigger a large resynchronization jump.
  - *Panic-mode*: on anything else, tokens are discarded up to the next `;`,
    `{`, `}` or EOF, and parsing resumes from there — so the parser never
    stops at the first error.
- **Structured error objects** (`mcl_errors.py`): every recovery event is a
  `SyntaxErrorRecord` with `expected_token`, `actual_token`, `line`, `column`,
  `recovery_action`, and a source `snippet` — never a raw message string —
  ready to be handed to the Phase 2 repair pipeline described below.

## What is intentionally NOT in this prototype

Per Section 13, the AI repair layer and the self-validating fix loop are
**Phase 2/3** work and are not implemented here. This prototype is lexer +
parser + recovery only. Specifically, not yet built:

- The **corruption engine** that generates a labeled (error, fix) dataset by
  programmatically breaking valid MCL programs.
- The **LoRA fine-tuning pipeline** that adapts a small pretrained code model
  (Qwen2.5-Coder-0.5B-Instruct primary, CodeT5+ 220M fallback) on that dataset.
- The **self-validating fix loop** (apply patch → re-parse → verified/unverified).
- The **evaluation harness** comparing the fine-tuned model against its own
  un-tuned base model.

## Roadmap (Phase 2 / Phase 3)

| Phase | Deliverable | Depends on |
|---|---|---|
| 2 | Corruption engine + synthetic dataset generator | This repo's parser/recovery pipeline (reused as the labeling oracle) |
| 2 | LoRA fine-tuning script (Hugging Face Transformers + PEFT) | The generated dataset |
| 3 | Self-validating fix loop wired into `main.py` | The fine-tuned model |
| 3 | Evaluation report (verified-fix rate, exact-match rate, fine-tuned vs. baseline) | The fix loop |

See the Phase 1 report's Sections 9.3–9.6 for the full design of each of
these, including the exact corruption taxonomy and evaluation metrics.

## Project layout

```
mcl_compiler/
├── mcl_lexer.py        # Tokenizer + LexicalError
├── mcl_ast.py           # AST node dataclasses
├── mcl_errors.py         # SyntaxErrorRecord (structured diagnostic object)
├── mcl_parser.py         # Recursive-descent parser + panic-mode/phrase-level recovery
├── ast_printer.py        # Indented AST pretty-printer (demo only)
├── main.py                # CLI demo: run lexer+parser on a .mcl file
├── tests/
│   ├── test_lexer.py
│   ├── test_parser.py
│   └── programs/
│       ├── valid_basic.mcl            # clean program, no errors
│       ├── malformed_multi_error.mcl  # 4 independent errors, recovered in one pass
│       └── lexical_error.mcl          # illegal char + malformed literal
├── README.md              # this file
├── CODE_EXPLAINED.md       # line-by-line walkthrough of every module
└── HOW_TO_RUN.md            # step-by-step run guide with expected output
```

## Running it

Requires Python 3.9+ and `pytest` (for the test suite only; the compiler
itself has no dependencies).

```bash
# Run the demo on a clean program
python main.py tests/programs/valid_basic.mcl

# Run the demo on a program with several independent syntax errors —
# watch it report all of them in a single pass instead of stopping at #1
python main.py tests/programs/malformed_multi_error.mcl

# Run the unit tests
pytest tests/ -v
```

### Sample output (multi-error recovery)

Running `malformed_multi_error.mcl` (missing `;`, missing `)`, a missing
`{` on a `while` body, and a stray unmatched `}`) reports **all four**
errors in one pass and still produces AST nodes for every statement that
could be recovered around them — no fix-recompile-fix cycle required.

## Design notes / how this maps to the Phase 1 report

| Report section | Where it lives |
|---|---|
| 9.1 Source language spec | Token types + grammar comments in `mcl_lexer.py` / `mcl_parser.py` |
| 9.2 Error recovery strategy | `Parser._expect()` (phrase-level) and `Parser._panic_mode()` |
| Structured error object | `mcl_errors.SyntaxErrorRecord` |
| AST | `mcl_ast.py`, built incrementally, `ErrorNode` marks unrecoverable gaps |
| 9.3 Corruption engine & dataset | Not yet implemented — planned for Phase 2 |
| 9.4 LoRA-fine-tuned repair model | Not yet implemented — planned for Phase 2 |
| 9.5 Self-validating fix loop | Not yet implemented — planned for Phase 3 |
| 9.6 Evaluation vs. baseline | Not yet implemented — planned for Phase 3 |

For the full walkthrough of every line in the current codebase, see
`CODE_EXPLAINED.md`; for exact commands and expected output, see
`HOW_TO_RUN.md`.
