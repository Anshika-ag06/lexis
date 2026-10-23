# CODE_EXPLAINED.md: Module Walkthrough

What each file does and why, in the order you would naturally read them:
lexer, AST, errors, parser, demo, tests, then the Phase 2 and Phase 3 modules.

---

## 1. `mcl_lexer.py`: the lexical analyzer

**Job:** turn raw source text into a flat list of `Token` objects.

- **`TokenType` enum.** Every token kind: keywords (`IF`, `WHILE`, `INT`, ...), `IDENT`,
  `NUMBER`, operators (`PLUS`, `EQ`, `AND`, ...), delimiters (`LPAREN`, `SEMI`, ...) and `EOF`.
  An enum means a typo like `TokenType.SEMII` fails immediately instead of silently.
- **`KEYWORDS`.** Maps `"if"`, `"while"`, ... to their token types. After reading a run of
  letters the lexer looks the text up here: found means keyword, not found means `IDENT`.
- **`SYMBOLS`.** An *ordered* list in which two-character operators (`==`, `!=`, `<=`, `>=`,
  `&&`, `||`) come before their one-character prefixes. The lexer takes the first match, so
  `==` is never read as two `=` signs. This is the longest-match rule.
- **`Token`.** A dataclass with `type`, `lexeme`, `line`, `column`.
- **`LexicalError`.** Raised for an illegal character (`@`, `$`) or a malformed number
  (`12abc`). It carries message, line, column and the source line. Lexical errors are fatal
  in this project, because recovering from a bad character means guessing intent.
- **`Lexer`.**
  - `_peek(offset)` looks ahead without consuming; `_advance()` consumes one character and
    updates `line` / `col` (a newline bumps `line` and resets `col` to 1).
  - `_skip_whitespace_and_comments()` eats spaces, tabs, newlines and `//` comments.
  - `next_token()` skips whitespace, then dispatches on the first character:
    letter or `_` reads an identifier or keyword; a digit reads a number and raises
    `LexicalError` if a letter follows directly; otherwise it scans `SYMBOLS` in order;
    if nothing matches the character is illegal.
  - `tokenize()` calls `next_token()` until `EOF` and returns the list.

---

## 2. `mcl_ast.py`: AST node types

Each node is a small `@dataclass` that also carries its `line`.

| Node | Holds | Grammar rule |
|---|---|---|
| `Program` | list of statements | program |
| `Decl` | `var_type`, `name`, `expr` | declaration |
| `Assign` | `name`, `expr` | assignment |
| `If` | `cond`, `then_block`, `else_block` | if / else |
| `While` | `cond`, `body` | while |
| `Print` | `expr` | print |
| `BinaryOp` | `op`, `left`, `right` | any binary expression |
| `Literal` | `value`, `kind` | number or `true` / `false` |
| `Identifier` | `name` | variable reference |
| `ErrorNode` | `note` | a statement the parser could not recover |

`ErrorNode` is not language syntax. It marks *where* parsing failed so the tree does not
silently get shorter and hide the gap.

---

## 3. `mcl_errors.py`: the structured error object

`SyntaxErrorRecord` has exactly six fields: `expected_token`, `actual_token`, `line`,
`column`, `recovery_action`, `snippet`. It is a dataclass, not a formatted string, so the
repair layer can call `to_dict()` and pass JSON to a strategy without parsing text.
`__str__` gives the human-readable form used by the CLI.

---

## 4. `mcl_parser.py`: recursive-descent parser and recovery engine

It follows the grammar, builds the AST, and recovers from errors instead of stopping.

### Constants
- `STATEMENT_START`: tokens that can begin a statement (`int`, `bool`, `if`, `while`,
  `print`, identifier). Used to decide whether a `;` was probably just forgotten.
- `SYNC_TOKENS`: `;`, `{`, `}`, `EOF`. The "safe landing" points for panic-mode.
- `COMPARISON_OPS`: operators handled at the `expr` level. Note that `NEQ` is not yet in
  this set (see the README known limitations).

### Helpers
`_peek`, `_advance`, `_check` work over the token list. `_record_error(...)` builds a
`SyntaxErrorRecord` and appends it to `self.errors`; every recovery path goes through it.

### `_expect(ttype, display)`: the central recovery decision
1. Token present: consume it, no error.
2. Expected `;` and the current token starts a statement, is `}` or is `EOF`: record a
   phrase-level error, consume nothing, continue. The error is reported at the *next* token,
   which is why a missing `;` on line 1 is reported at line 2.
3. Expected `)` and the current token is `{` or `;`: same phrase-level handling.
4. Otherwise record a panic-mode error and call `_panic_mode()`.

### `_panic_mode()`
Discards tokens until a sync token appears. It **always discards one token first**, so a
stray `}` (already a sync token) cannot make the parser loop forever on the same token. If it
stops on `;` it consumes it so the next statement starts cleanly.

### Grammar methods
`_parse_statement` dispatches on the first token to `_parse_decl`, `_parse_assign`,
`_parse_if`, `_parse_while`, `_parse_print`. A token that starts no statement records an
error, runs panic-mode and returns an `ErrorNode`. `_parse_block` handles `{ ... }` and
reports a missing `{` or `}`.

### Expression methods
```
expr   -> term   { (+ - == < > <= >= && ||) term }   loosest binding
term   -> factor { (* /) factor }
factor -> IDENT | NUMBER | true | false | ( expr )   tightest binding
```
`_parse_expr` only calls `_parse_term`, which only calls `_parse_factor`, so `*` and `/`
end up deeper in the tree than `+` and `-`. That is what "higher precedence" means in AST
form (`1 + 2 * 3` has `+` at the root).

---

## 5. `ast_printer.py`: demo-only pretty printer

Walks the AST recursively and prints it with indentation. It is not part of the compiler
pipeline; without it you would still get an AST object, just not a readable printout.

---

## 6. `main.py`: the CLI driver

1. Read the `.mcl` file.
2. Tokenize. A `LexicalError` is printed and the run stops.
3. Print the tokens.
4. Parse with recovery.
5. Print the AST and every structured error.
6. Print a one-line summary.

Run: `python3 main.py <file.mcl>`.

---

## 7. Phase 2 and Phase 3 modules

| Component | Role |
|---|---|
| `corruption_engine.py` | Applies **one** controlled, reversible fault to a valid program (delete `;`, delete `)` or brace, replace a token, insert a stray token). Same seed plus same source gives the same corrupted file; the gold fix is the exact inverse edit. |
| `dataset_builder.py` | Builds labelled samples with `source`, `corrupted`, `diagnostic`, `gold_fix`. One fault per sample is checked with an AST diff. |
| `validate_fix.py` | The verification step: lex and parse the patched program; zero errors gives `VERIFIED`, otherwise `UNVERIFIED` and the patch is discarded. |
| Symbol table | Scoped map from declared names to types; used by semantic analysis. |
| Semantic analysis | Detects undeclared variables, redeclarations and type mismatches. |
| Three-address code | Walks the AST post-order, creating temporaries and labels / jumps for `if` and `while`. |
| DOT export | Writes the AST as Graphviz DOT for diagrams. |
| Repair strategies | Rules (deterministic fix from the error record), zero-shot LLM, few-shot LLM (examples from the dataset), hybrid (rules first, LLM fallback). LLM calls use `qwen2.5:3b` through Ollama. |
| Evaluation harness | Runs each strategy on the same 100 test examples and reports verified-fix rate and exact-match rate. |
| `train_lora.py` | LoRA training script written for the original plan. The Colab run could not be completed, so it is not part of the final results. |

The repair loop is: parse the broken program, collect structured errors, ask a strategy for a
patch, re-parse the patch, label it. The compiler is the judge at every step.

---

## 8. Tests (`tests/`)

- `test_lexer.py` covers keywords and identifiers, longest-match operators, boolean literals,
  comment skipping, line / column tracking, illegal characters and malformed numbers.
- `test_parser.py` covers a valid program, precedence, missing `;` (phrase-level), missing `)`,
  multiple independent errors in one pass, invalid statement start (panic-mode and
  `ErrorNode`), and the six fields of the error record.
- Phase 2 and 3 tests cover corruption determinism, single-fault samples, dataset schema,
  and the validation logic (a good fix is `VERIFIED`, a wrong fix stays `UNVERIFIED`).
- `tests/programs/` holds the three demo programs.

---

## Design decisions worth knowing

**Lexical errors are fatal, syntax errors are recovered.** The project is about syntax
recovery. Recovering from an illegal character needs a guess at what was meant, which is a
separate problem and listed as future work.

**Panic-mode always consumes one token.** An early version could spin forever on a stray
unmatched `}`: it was already a sync token, so the skip loop did nothing and the outer loop
never advanced. Forcing at least one discard guarantees progress.

**The error record is an object.** Keeping it structured is what lets the repair layer
consume errors programmatically.

**Verified versus exact match.** Verified means the patch parses; exact means it equals the
original program. They are reported separately because a repair can be valid but unfaithful.

**LoRA replaced by pretrained-model repair.** The fine-tuning run could not be completed on
Colab, so the project used its planned fallback. The verification loop is unchanged.
