"""
mcl_rule_repair.py
------------------
Repair method A: no AI at all.

Idea: a syntax error almost always has a small local cause. So we try a short
list of tiny edits near the place the parser complained (insert a ';', insert
or delete a ')', add a '{' or '}', add a missing '=', fix a misspelled
keyword, turn '=' into '==' in a condition) and keep an edit only if the
real compiler front end then reports FEWER errors. Repeat until the program
passes or nothing helps.

This is the same "propose a fix, then verify it with the compiler" idea as the
LLM fix loop, with a hand-written proposer instead of a model, so the two can
be compared fairly on the same test set.

The verifier is `check_source`, so a "verified" repair here means exactly what
it means everywhere else in the project: the lexer, parser and semantic
analyzer all accept it.
"""

import re
from dataclasses import dataclass, field
from typing import List, Tuple

from mcl_check import CheckResult, check_source
from mcl_prompt import normalize_program

KEYWORDS = ["if", "else", "while", "print", "int", "bool"]
_OPERATOR_EQ = re.compile(r"(?<![=<>!])=(?!=)")

# which edit family to try first for each kind of parser complaint
_FAMILY_FOR_EXPECTED = {
    "';'": "semicolon",
    "')'": "rparen",
    "'('": "lparen",
    "'{'": "lbrace",
    "'}'": "rbrace",
    "'='": "assign",
}


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _brace_depth(lines: List[str], upto: int) -> int:
    text = "\n".join(lines[:upto])
    return text.count("{") - text.count("}")


def _indent_for_closing_brace(lines: List[str], position: int) -> str:
    return "    " * max(_brace_depth(lines, position) - 1, 0)


Candidate = Tuple[str, str, str]   # (family, description, new_source)


def candidate_edits(source: str, check: CheckResult) -> List[Candidate]:
    """Every small edit worth trying for the first reported syntax error."""
    if check.lex_error is not None or not check.syntax_errors:
        return []
    err = check.syntax_errors[0]
    lines = source.split("\n")
    centre = min(max(err.line - 1, 0), len(lines) - 1)
    window = range(max(0, centre - 2), min(len(lines), centre + 2))
    out: List[Candidate] = []

    def replace_line(i: int, new_line: str, family: str, why: str):
        new = lines.copy()
        new[i] = new_line
        out.append((family, f"{why} (line {i + 1})", "\n".join(new)))

    for i in window:
        line = lines[i]
        body = line.rstrip()
        stripped = body.strip()
        if not stripped:
            continue

        # missing ';'
        if not body.endswith((";", "{", "}")):
            replace_line(i, body + ";", "semicolon", "insert ';' at end of line")

        # missing ')' : try closing at the end of each chunk of the line. Positions
        # that wrap a whole expression (more than one token) come first, earliest
        # first; closing around a single operand, as in "(x) * x", is tried last.
        stack: List[int] = []
        for k, ch in enumerate(body):
            if ch == "(":
                stack.append(k)
            elif ch == ")" and stack:
                stack.pop()
        open_idx = stack[-1] if stack else -1
        positions = [pos for pos in range(1, len(body) + 1)
                     if body[pos - 1] != " " and (pos == len(body) or body[pos] in " ;{")]
        wraps = [p for p in positions if p > open_idx and " " in body[open_idx + 1:p].strip()]
        for pos in wraps + [p for p in positions if p not in wraps]:
            replace_line(i, body[:pos] + ")" + body[pos:], "rparen", "insert ')'")

        # extra ')' : try deleting each one
        for pos in range(len(line) - 1, -1, -1):          # rightmost first
            if line[pos] == ")":
                rest = line[pos + 1:]
                if not line[:pos].strip():           # stray ')' at the start of the line
                    rest = line[:pos] + rest.lstrip()
                    replace_line(i, rest, "rparen_extra", "delete a ')'")
                else:
                    replace_line(i, line[:pos] + rest, "rparen_extra", "delete a ')'")

        # missing '{' after if / while / else
        if re.match(r"^\s*(\}\s*)?(if|while|else)\b", line) and not body.endswith("{"):
            replace_line(i, body + " {", "lbrace", "insert '{' at end of line")

        # missing '=' in a declaration or assignment
        m = re.match(r"^(\s*(?:int|bool)\s+\w+)\s+(?!=)(\S.*)$", line)
        if m:
            replace_line(i, f"{m.group(1)} = {m.group(2)}", "assign", "insert '=' in declaration")
        m = re.match(r"^(\s*(?!(?:if|while|print|else|int|bool)\b)[A-Za-z_]\w*)\s+(?!=)([^=\s].*;)$", line)
        if m:
            replace_line(i, f"{m.group(1)} = {m.group(2)}", "assign", "insert '=' in assignment")

        # misspelled keyword at the start of a line (also after a leading '}')
        m = re.match(r"^(\s*(?:\}\s*)?)([A-Za-z_]\w*)(.*)$", line)
        if m and m.group(2) not in KEYWORDS and not re.match(r"\s*=(?!=)", m.group(3)):
            near = sorted(((edit_distance(m.group(2), kw), kw) for kw in KEYWORDS))
            for dist, kw in near:
                if dist <= 2 and len(m.group(2)) > 1:
                    replace_line(i, f"{m.group(1)}{kw}{m.group(3)}", "keyword",
                                 f"change '{m.group(2)}' to '{kw}'")

        # '=' written where '==' was meant. In a condition any single '=' may be wrong;
        # in a declaration or assignment the first '=' is the real assignment.
        matches = list(_OPERATOR_EQ.finditer(line))
        if not stripped.startswith(("if", "while")):
            matches = matches[1:]
        for mt in matches:
            replace_line(i, line[:mt.start()] + "==" + line[mt.end():], "equals", "change '=' to '=='")

    # missing '}' : refill a blank line, insert before a nearby line, or append at the
    # end. When the parser ran into the end of the file, appending comes first.
    rbrace: List[Candidate] = []
    for j, line in enumerate(lines):
        if not line.strip():
            new = lines.copy()
            new[j] = _indent_for_closing_brace(lines, j) + "}"
            rbrace.append(("rbrace", f"put '}}' back on blank line {j + 1}", "\n".join(new)))
    for p in list(window):
        new = lines.copy()
        new.insert(p, _indent_for_closing_brace(lines, p) + "}")
        rbrace.append(("rbrace", f"insert '}}' before line {p + 1}", "\n".join(new)))
    # indentation prior: a block ends where the indentation drops. A drop to a
    # statement means a '}' is missing before it; a drop of two levels to a '}'
    # means an inner '}' is missing. The brace sits one level left of the line above.
    def _ind(text: str) -> int:
        return len(text) - len(text.lstrip())

    indent_candidates: List[Candidate] = []
    for k in range(1, len(lines)):
        if not lines[k].strip() or not lines[k - 1].strip():
            continue
        drop = _ind(lines[k - 1]) - _ind(lines[k])
        closes = lines[k].lstrip().startswith("}")
        if drop >= (8 if closes else 4):
            new = lines.copy()
            new.insert(k, " " * (_ind(lines[k - 1]) - 4) + "}")
            indent_candidates.append(("rbrace", f"insert '}}' where the indentation drops (line {k + 1})",
                                      "\n".join(new)))
    at_end = lines + [_indent_for_closing_brace(lines, len(lines)) + "}"]
    end_candidate = ("rbrace", "append '}' at the end of the file", "\n".join(at_end))
    if err.actual_token == "<EOF>":
        out.extend(indent_candidates + [end_candidate] + rbrace)
    else:
        out.extend(indent_candidates + rbrace + [end_candidate])

    # try the family that matches the parser's complaint first; sort is stable
    expected_family = _FAMILY_FOR_EXPECTED.get(err.expected_token)
    out.sort(key=lambda c: 0 if c[0] == expected_family else 1)
    return out


def _score(res: CheckResult) -> Tuple[int, int]:
    """Lower is better: syntax problems first, then total problems."""
    return (len(res.syntax_errors) + (1 if res.lex_error else 0), res.error_count)


@dataclass
class RuleRepairResult:
    status: str                         # "already-valid" | "verified" | "unverified"
    original: str
    repaired: str
    steps: List[str] = field(default_factory=list)


def rule_repair(source: str, max_iterations: int = 8) -> RuleRepairResult:
    current = normalize_program(source)
    check = check_source(current)
    if check.ok:
        return RuleRepairResult("already-valid", current, current)

    steps: List[str] = []
    for _ in range(max_iterations):
        if check.ok:
            break
        best = None
        for _family, why, cand in candidate_edits(current, check):
            cand = normalize_program(cand)
            res = check_source(cand)
            if best is None or _score(res) < _score(best[2]):
                best = (why, cand, res)
        if best is None or _score(best[2]) >= _score(check):
            break
        steps.append(best[0])
        current, check = best[1], best[2]

    return RuleRepairResult("verified" if check.ok else "unverified", normalize_program(source), current, steps)
