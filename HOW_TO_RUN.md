# HOW_TO_RUN.md — Step-by-Step Guide

## 0. Requirements

- Python 3.9 or newer (check with `python3 --version`)
- `pytest`, only needed if you want to run the automated test suite

No other dependencies — the compiler itself (lexer/parser) is pure
Python with nothing to install.

## 1. Unzip / open the project

```bash
unzip mcl_compiler_phase1.zip
cd mcl_compiler
```

You should see this layout:

```
mcl_compiler/
├── mcl_lexer.py
├── mcl_ast.py
├── mcl_errors.py
├── mcl_parser.py
├── ast_printer.py
├── main.py
├── requirements.txt
├── README.md
├── CODE_EXPLAINED.md
├── HOW_TO_RUN.md      (this file)
└── tests/
    ├── test_lexer.py
    ├── test_parser.py
    └── programs/
        ├── valid_basic.mcl
        ├── malformed_multi_error.mcl
        └── lexical_error.mcl
```

## 2. Run the demo on a clean program

```bash
python3 main.py tests/programs/valid_basic.mcl
```

**What you'll see, in order:**
1. The source file printed back.
2. `=== Tokens ===` — every token the lexer produced, with type,
   text, and line:column.
3. `=== AST ===` — the parsed tree, indented by nesting level.
4. `=== Recovered Errors (0) ===` — empty, because this file is valid
   MCL.
5. A one-line summary (`0 syntax error(s) recovered...`).

## 3. Run the demo on a program with multiple errors

```bash
python3 main.py tests/programs/malformed_multi_error.mcl
```

This file has four independent, unrelated mistakes:
- a missing `;` after `int x = 5`
- a missing `)` on an `if (...`
- a missing `{` on a `while` body
- a stray, unmatched `}`

**Expected output** (the important part, `=== Recovered Errors (4) ===`):

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

This is the headline demo for your review: **one run, four independent
errors reported, parsing never stopped early** — exactly the problem
statement from the Phase 1 report (a naive parser would have stopped
after error #1 and needed four separate fix-recompile cycles).

## 4. Run the demo on a program with a lexical error

```bash
python3 main.py tests/programs/lexical_error.mcl
```

This file has a malformed numeric literal (`12abc`). Lexical errors are
fatal in this prototype (see `CODE_EXPLAINED.md` for why), so you'll see:

```
LEXICAL ERROR: Malformed numeric literal '12abc' at line 2, column 9
    int y = 12abc;
```

## 5. Try your own file

Write any `.mcl` file (see the grammar in `README.md` or the sample
programs for syntax) and run:

```bash
python3 main.py path/to/your_file.mcl
```

## 6. Run the automated test suite

```bash
pip install -r requirements.txt --break-system-packages   # if pytest isn't installed
pytest tests/ -v
```

**Expected output:** all 14 tests pass, e.g.

```
tests/test_lexer.py::test_keywords_and_identifiers PASSED
tests/test_lexer.py::test_multi_char_operators_prefer_longest_match PASSED
...
tests/test_parser.py::test_multiple_independent_errors_recovered_in_one_pass PASSED
tests/test_parser.py::test_structured_error_object_fields PASSED

14 passed in 0.02s
```

## 7. What to show live in your review

If you only have time to run two things, run these, in this order:

1. `python3 main.py tests/programs/valid_basic.mcl` — proves the lexer
   and parser correctly handle every construct in the grammar (decl,
   assign, if/else, while, print, expressions).
2. `python3 main.py tests/programs/malformed_multi_error.mcl` — proves
   the actual point of the project: multi-error recovery in a single
   pass, with a structured error object for each one.

Then optionally `pytest tests/ -v` to show the automated coverage behind
both of those demos.
