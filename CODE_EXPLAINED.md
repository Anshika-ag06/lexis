# CODE_EXPLAINED.md — Walkthrough of Every File

This document explains what each file does and why, in the order you'd
naturally read them (lexer → AST → errors → parser → demo → tests). Use
this to explain the code to your professor or just to refresh your own
understanding before the review.

---

## 1. `mcl_lexer.py` — the Lexical Analyzer

**Job:** turn raw source text into a flat list of `Token` objects.

### The `TokenType` enum
Every kind of token MCL can have — keywords (`IF`, `WHILE`, `INT`...),
literals (`IDENT`, `NUMBER`), operators (`PLUS`, `EQ`, `AND`...), and
delimiters (`LPAREN`, `SEMI`...). Using an `Enum` instead of raw strings
means the parser can never accidentally typo a token type — Python will
error immediately if you misspell `TokenType.SEMII`.

### `KEYWORDS` dict
Maps the literal text `"if"`, `"while"`, etc. to their `TokenType`. When
the lexer reads a run of letters, it looks the text up here — found →
it's a keyword; not found → it's an identifier (a variable name).

### `SYMBOLS` list
This is the important design detail: it's ordered so that **two-character
operators come before their one-character prefixes** — `"=="` is checked
before `"="`, `"<="` before `"<"`, and so on. If you checked `"="` first,
the lexer would greedily consume just the first `=` of `==` and leave a
stray second `=` behind. The lexer walks this list top-to-bottom and
takes the first match, which is why order matters here.

### `Token` dataclass
Just a labeled bundle: `type`, `lexeme` (the actual text, e.g. `"123"`),
and `line`/`column` (for error messages later). A `@dataclass` auto-
generates `__init__` so we don't write boilerplate.

### `LexicalError` exception
Raised for genuinely broken input — an illegal character (`@`, `$`, ...)
or a malformed number literal like `12abc`. Unlike syntax errors, lexical
errors are treated as fatal in this prototype (see "Design decisions"
below for why).

### `Lexer` class — the actual scanning logic
- `_peek(offset)` — look at a character without consuming it.
- `_advance()` — consume one character, and update `line`/`col`
  (resetting `col` to 1 and bumping `line` whenever we cross a `\n`).
- `_skip_whitespace_and_comments()` — eats spaces, tabs, newlines, and
  `//` line comments before every token, so the rest of the lexer never
  has to think about them.
- `next_token()` — the heart of the lexer. Looking at the current
  character, it decides what kind of token is starting:
  - **letter or `_`** → keep consuming letters/digits/`_` → check
    `KEYWORDS` → emit `IDENT` or the matching keyword token.
  - **digit** → keep consuming digits. If a letter immediately follows
    (like the `abc` in `12abc`), that's a malformed literal → raise
    `LexicalError`. Otherwise emit `NUMBER`.
  - **otherwise** → try every entry in `SYMBOLS` in order; first match
    wins.
  - **nothing matched** → the character is illegal → raise
    `LexicalError`.
- `tokenize()` — just calls `next_token()` in a loop until it returns
  `EOF`, and returns the whole list. This is what `main.py` calls.

---

## 2. `mcl_ast.py` — the AST Node Types

Each node is a tiny `@dataclass` — a labeled box holding whatever data
that grammar rule needs:

| Node | Holds | Grammar rule |
|---|---|---|
| `Program` | list of statements | `<program>` |
| `Decl` | var_type, name, expr | `<decl>` |
| `Assign` | name, expr | `<assign>` |
| `If` | cond, then_block, else_block | `<if>` |
| `While` | cond, body | `<while>` |
| `Print` | expr | `<print>` |
| `BinaryOp` | op, left, right | any `+ - * / == < > && \|\|` expression |
| `Literal` | value, kind | a number or `true`/`false` |
| `Identifier` | name | a variable reference |
| `ErrorNode` | note | a statement the parser gave up on, even after recovery |

`ErrorNode` is the one node that doesn't correspond to real language —
it's a placeholder so the AST still shows *where* something couldn't be
parsed, instead of silently producing a shorter tree and hiding the gap.

---

## 3. `mcl_errors.py` — the Structured Error Object

This is a direct implementation of the `{ expectedToken, actualToken,
line, column, recoveryAction, snippet }` object from your Phase 1
report, Section 9.2. It's a `@dataclass` (not a formatted string)
specifically so a later stage — the LLM diagnostic module in Phase 2 —
can do `error.to_dict()` and hand it straight to an API call as JSON,
instead of having to regex-parse a message.

`__str__` just gives a nicely formatted version for the human-readable
CLI output in `main.py`.

---

## 4. `mcl_parser.py` — the Recursive-Descent Parser + Recovery Engine

This is the biggest and most important file. It has three jobs at once:
follow the grammar, build the AST, and recover from errors instead of
stopping.

### Constants at the top
- `STATEMENT_START` — the set of token types that can legally begin a
  new statement (`int`, `bool`, `if`, `while`, `print`, or an
  identifier). Used to guess "did they just forget a `;`?"
- `SYNC_TOKENS` — the "safe landing" tokens panic-mode looks for:
  `;`, `{`, `}`, or end-of-file.
- `COMPARISON_OPS` — every operator that can appear at the `<expr>`
  precedence level (as opposed to `<term>`, which only has `*` `/`).

### Token-stream helpers
`_peek`, `_advance`, `_check` mirror the lexer's helpers but operate over
the token list instead of raw characters — the parser never looks at
source text directly, only at tokens.

### `_record_error(...)`
Builds a `SyntaxErrorRecord` from the current token and appends it to
`self.errors`. Every single recovery path in the file funnels through
this one method, which is what guarantees every error — no matter which
grammar rule triggered it — ends up in the same structured list.

### `_expect(ttype, display)` — the key recovery decision point
This is called every time the grammar expects one specific token (a
`;`, a `)`, an `=`). It tries three things in order:

1. **It's actually there** → consume it, done, no error.
2. **Phrase-level fix for a missing `;`** — if we expected `;` but the
   current token looks like the start of the *next* statement (or the
   end of a block, or EOF), we assume the `;` was simply forgotten and
   quietly continue — *without* consuming or skipping anything. This is
   the "insert a virtual token" idea from Section 9.2.
3. **Phrase-level fix for a missing `)`** — same idea: if we expected `)`
   but landed on `{` or `;`, assume it was omitted.
4. **Nothing safe to do locally** → fall back to `_panic_mode()`.

### `_panic_mode()`
Discards tokens until it finds a `;`, `{`, `}`, or EOF. Two important
details:
- It **always discards at least one token first**, even if the current
  token already happens to be a sync token. This matters for a case
  like a stray extra `}` sitting at the top level with nothing to
  recover from — without this rule, the parser could get stuck forever
  re-examining the same token. (This was actually a real bug caught
  while testing — see "Design decisions" below.)
- If it lands exactly on a `;`, it consumes that too, so the *next*
  statement starts on a clean token.

### The grammar methods (`_parse_statement`, `_parse_decl`, `_parse_assign`,
`_parse_if`, `_parse_while`, `_parse_print`, `_parse_block`)
Each one is a direct translation of one grammar rule from Section 9.1 —
read the token(s) the rule requires, call `_expect()` for the punctuation,
recurse into sub-rules for nested expressions/blocks, and return the
matching AST node. `_parse_statement` is the dispatcher: it looks at the
current token and decides which of the other five methods to call based
on `STATEMENT_START`. If the token doesn't match anything, that's an
"unknown start of statement" error → record it → panic-mode → return an
`ErrorNode`.

### The expression methods (`_parse_expr`, `_parse_term`, `_parse_factor`)
These three implement operator precedence the classic recursive-descent
way — a chain of three levels, low to high precedence:

```
expr   → term   { (+ - == < > && ||) term }    (loosest binding)
term   → factor { (* /) factor }
factor → IDENT | NUMBER | true | false | ( expr )   (tightest binding)
```

Because `_parse_expr` only ever calls `_parse_term` (never the other way
around), and `_parse_term` only ever calls `_parse_factor`, `*`/`/`
naturally end up nested *inside* `+`/`-` in the resulting tree — which is
exactly what "multiplication binds tighter than addition" means in AST
form. (There's a test for this: `test_expression_precedence`.)

---

## 5. `ast_printer.py` — Demo-Only Pretty Printer

Purely cosmetic: walks the AST recursively and prints it with
indentation so you can actually read the tree in the terminal. It isn't
part of the compiler pipeline itself — you could delete this file and
the compiler would still fully work, you'd just get a Python object back
instead of a nice printout.

---

## 6. `main.py` — the CLI Demo

Ties everything together for one `.mcl` file:
1. Read the file.
2. Run it through `Lexer(...).tokenize()`. If a `LexicalError` is
   raised, print it and stop (lexical errors are fatal here).
3. Print every token.
4. Run the tokens through `Parser(...).parse_program()`.
5. Print the AST (`print_ast`) and every recovered error
   (`parser.errors`).
6. Print a one-line summary.

This is the file you actually run (`python main.py <file>`).

---

## 7. `tests/test_lexer.py` and `tests/test_parser.py`

Standard `pytest` test files. A few worth knowing about specifically:

- `test_multi_char_operators_prefer_longest_match` — proves the
  `SYMBOLS` ordering trick actually works (`==` isn't mistaken for two
  `=`s).
- `test_missing_semicolon_is_phrase_level_recovered_and_parsing_continues`
  and `test_missing_closing_paren_is_phrase_level_recovered` — prove the
  phrase-level recovery paths in `_expect()`.
- `test_multiple_independent_errors_recovered_in_one_pass` — the whole
  point of the project: feeds in a file with *two* unrelated mistakes and
  checks the parser reports both and still parses everything after them.
- `test_invalid_statement_start_triggers_panic_mode_and_error_node` —
  proves panic-mode kicks in and produces an `ErrorNode` placeholder
  rather than crashing or silently dropping the line.
- `test_structured_error_object_fields` — proves `SyntaxErrorRecord` has
  exactly the six fields the Phase 1 report promises, nothing more or
  less.

---

## Design decisions worth mentioning in your review

**Why are lexical errors fatal but syntax errors are recovered?**
The Phase 1 report's recovery objectives (Section 9.2) are specifically
about *syntax* recovery — panic-mode and phrase-level are parsing
concepts. Recovering from a *lexical* error (an illegal character) well
enough to keep tokenizing meaningfully is a separate, harder problem
(you'd have to guess what the bad character was supposed to be). Keeping
lexical errors fatal for this prototype keeps the scope matched to what
was proposed, and it's flagged in the README as a place Phase 2 could
extend if you want to.

**The panic-mode "always advance at least one token" rule.**
While testing against a file with a genuinely unmatched `}`, the very
first version of `_panic_mode()` could get stuck: if the parser hit an
error exactly *on* a token that was already a sync token (like a stray
`}` with nothing to close), the "skip until you see a sync token" loop
would immediately see it was already there and do nothing — so the
outer parsing loop never moved forward and looped forever on the same
token. Forcing at least one token to always be discarded fixes this and
is a fairly standard real-world panic-mode detail (compilers like GCC's
recovery do the same "always consume something" guarantee).
