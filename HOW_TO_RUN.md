# HOW_TO_RUN.md: Commands and Expected Output

## 0. Requirements

- Python 3.9 or newer (`python3 --version`)
- `pytest`, only for the automated tests
- **Optional, for LLM repair strategies only:** [Ollama](https://ollama.com) with the
  `qwen2.5:3b` model

The compiler itself (lexer, parser, recovery) is pure Python with nothing to install.

## 1. Get the project

```bash
git clone https://github.com/Anshika-ag06/lexis.git
cd lexis
```

Main files: `mcl_lexer.py`, `mcl_ast.py`, `mcl_errors.py`, `mcl_parser.py`,
`ast_printer.py`, `main.py`, `requirements.txt`, `tests/` (with `programs/`).

## 2. Clean program

```bash
python3 main.py tests/programs/valid_basic.mcl
```

You will see, in order: the source, `=== Tokens ===`, `=== AST ===`,
`=== Recovered Errors (0) ===` with "(none, program parsed cleanly)", and a summary line.

## 3. Program with several syntax errors (the headline demo)

```bash
python3 main.py tests/programs/malformed_multi_error.mcl
```

The file contains a missing `;`, a missing `)`, a missing `{` on a `while` body, and a stray
`}` (which also swallows a stray `)` in the same panic-mode jump). Expected key output:

```
=== Recovered Errors (4) ===

  Error #1
    [line 2:1] expected ';', found 'int' -> phrase-level: inserted missing ';'
        int y = 10;

  Error #2
    [line 4:11] expected ')', found '{' -> phrase-level: inserted missing ')'
        if (x < y {

  Error #3
    [line 9:5] expected '{', found 'x' -> panic-mode: resynchronizing at next ';' or block delimiter
            x = x + 1;

  Error #4
    [line 11:1] expected start of statement (decl/assign/if/while/print), found '}' -> panic-mode: resynchronizing at next ';' or block delimiter
        }

Summary: 4 syntax error(s) recovered in a single pass (7 top-level statement slots produced).
```

One run, four independent errors, parsing never stopped early. A naive parser would need
four fix-and-recompile cycles.

## 4. Program with a lexical error

```bash
python3 main.py tests/programs/lexical_error.mcl
```

Lexical errors are fatal by design, so the run stops at the first one:

```
LEXICAL ERROR: Malformed numeric literal '12abc' at line 2, column 9
    int y = 12abc;
```

## 5. Your own file

```bash
python3 main.py path/to/your_file.mcl
```

## 6. Unit tests

```bash
pip install -r requirements.txt --break-system-packages   # if pytest is missing
pytest tests/ -v
```

All tests should pass. The front-end suite alone is 14 tests, for example:

```
tests/test_lexer.py::test_keywords_and_identifiers PASSED
tests/test_lexer.py::test_multi_char_operators_prefer_longest_match PASSED
...
tests/test_parser.py::test_multiple_independent_errors_recovered_in_one_pass PASSED
tests/test_parser.py::test_structured_error_object_fields PASSED
```

Later-phase tests (corruption determinism, dataset schema, validation) run in the same command.

## 7. LLM repair strategies (optional)

Install and start Ollama, then pull the model used in the evaluation:

```bash
ollama pull qwen2.5:3b
ollama serve          # skip if Ollama is already running
```

Then run your repair or evaluation script from the repository root:

```bash
python3 <your_repair_or_evaluation_script>.py
```

Strategies available: `rules`, `zero-shot`, `few-shot`, `hybrid`. Each proposed fix is
re-parsed and labelled `VERIFIED` or `UNVERIFIED`. Expected summary over the 100 test
examples:

| Strategy | Verified | Exact match |
|---|---|---|
| Hybrid | 99% | 93% |
| Rules | 97% | 91% |
| Few-shot | 85% | 70% |
| Zero-shot | 75% | 56% |

Rules need no model and run instantly. The LLM strategies take seconds per example on a laptop.

## 8. Troubleshooting

- **`ModuleNotFoundError: mcl_lexer`**: run commands from the repository root.
- **Connection refused when running LLM strategies**: Ollama is not running; start
  `ollama serve`.
- **Model not found**: run `ollama pull qwen2.5:3b`.
- **`pip` refuses to install**: add `--break-system-packages`, or use a virtual environment.

## 9. What to show live in your review

1. `python3 main.py tests/programs/valid_basic.mcl`: lexer and parser handle every construct.
2. `python3 main.py tests/programs/malformed_multi_error.mcl`: four errors in one pass.
3. `python3 main.py tests/programs/lexical_error.mcl`: a lexical error stops the run.
4. A repair run showing the patch, the re-parse and the `VERIFIED` label.
5. The 100-example comparison table.
6. `pytest tests/ -v` if time allows.
