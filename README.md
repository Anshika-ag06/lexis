# MCL Compiler: Intelligent Syntax Error Recovery with Self-Validating Repair

BCSE307P Compiler Design Laboratory.

A compiler front end for MCL (Mini Compiler Language) that does not stop at the
first error. It recovers from syntax mistakes, checks types and scopes, generates
three-address code, and can propose a repair for a broken program and then
**verify the proposal with the compiler itself**. Four repair methods are compared
on a held-out test set.

## What is in the project

| Stage | Files | Phase |
|---|---|---|
| Lexer, parser with panic-mode and phrase-level recovery, AST | `mcl_lexer.py` `mcl_parser.py` `mcl_ast.py` `mcl_errors.py` `ast_printer.py` | 1 |
| Symbol table, semantic analysis, three-address code, AST diagram, corruption engine | `mcl_symtable.py` `mcl_semantic.py` `mcl_irgen.py` `mcl_ast_dot.py` `mcl_corruption.py` | 2 |
| Verifier, prompt format, dataset builder, program generator | `mcl_check.py` `mcl_prompt.py` `build_dataset.py` `mcl_program_gen.py` | 3 |
| Repair methods and the self-validating fix loop | `mcl_rule_repair.py` `mcl_llm.py` `mcl_repair.py` | 3 |
| Evaluation | `evaluate_model.py` `compare_results.py` | 3 |

## The four repair methods

| Method | What proposes the fix |
|---|---|
| A. `rules` | Hand-written small edits near the error. No AI. |
| B. `ollama --shots 0` | A local LLM (Ollama) sees the program and the compiler's diagnostics. |
| C. `ollama --shots 3` | The same, plus 3 worked examples drawn only from the training split. |
| D. `hybrid` | Rules first; the LLM only when the rules cannot fix it. |

Every proposed fix goes back through the lexer, parser and semantic analyzer.
**Verified** means it passes all three. **Exact** means it equals the original
program. Several different programs can be valid, so exact is the stricter metric.

## Dataset

`build_dataset.py` takes valid programs (`dataset/programs/`, made by
`mcl_program_gen.py`), breaks them in nine ways, keeps only corruptions the real
parser rejects, and splits **by program** into train / validation / test so the
test programs are never seen in any form during development.
See `dataset/out/stats.json`.

## Running it

```bash
python3 -m pytest tests -q                                   # all tests
python3 main.py tests/programs/valid_basic.mcl               # lexer -> parser -> semantic -> TAC
python3 main.py tests/programs/malformed_multi_error.mcl --repair --method rules
python3 main.py tests/programs/malformed_multi_error.mcl --repair --method ollama --shots 3
python3 build_dataset.py                                     # rebuild the dataset
```

See `PHASE3_GUIDE.md` for the full evaluation run.

## Known limitations

- The corruptions are synthetic and partly mirror the rule-based repairs, so the
  benchmark favours method A. Real student mistakes would be messier.
- The test split is 6 programs (408 examples); some error types have few examples.
- `!=` is lexed but cannot yet be parsed in an expression (a Phase 1 grammar gap).
- Semantic errors report a line number but no column.
- Rule-based placement of a missing `)` or `}` relies on the program being
  indented consistently.
- No interpreter: three-address code is generated but not executed.

## Future work

`future_work/` holds an unfinished plan to fine-tune a small code model with LoRA.
It was never trained end to end and no reported result depends on it.
