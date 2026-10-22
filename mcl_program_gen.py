"""
mcl_program_gen.py
------------------
Generates varied, *valid* MCL programs to use as the clean "ground truth"
side of the training dataset.

Every generated program is run through the real compiler front end
(`check_source`) and is only kept if it has zero syntax and zero semantic
errors, so the generator can be sloppy and the verifier stays honest.

Parser quirk handled here: in this grammar '+', '-' and the comparison /
logical operators share one precedence level, so `a < b + c` would parse
as `(a < b) + c`. The generator therefore wraps any compound operand in
parentheses before using it inside a comparison or logical expression.

Usage:
    python mcl_program_gen.py --count 60 --out dataset/programs --seed 7
"""

import argparse
import os
import random
from typing import Dict, List, Optional

from mcl_check import check_source

NAMES = [
    "a", "b", "c", "x", "y", "z", "i", "j", "n", "sum", "total", "count",
    "limit", "step", "result", "temp", "score", "level", "size", "value",
    "flag", "done", "ok", "found", "ready", "active",
]


class _Generator:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.scopes: List[Dict[str, str]] = [{}]
        self.lines: List[str] = []
        self.used = set()
        self.indent = 0

    # -- helpers -----------------------------------------------------------
    def emit(self, text: str) -> None:
        self.lines.append("    " * self.indent + text)

    def visible(self, type_: str) -> List[str]:
        return [n for sc in self.scopes for n, t in sc.items() if t == type_]

    def fresh_name(self) -> str:
        free = [n for n in NAMES if n not in self.used]
        name = self.rng.choice(free) if free else f"v{len(self.used)}"
        self.used.add(name)
        return name

    @staticmethod
    def paren(expr: str) -> str:
        return expr if " " not in expr else f"({expr})"

    # -- expressions ---------------------------------------------------------
    def atom_int(self) -> str:
        vars_ = self.visible("int")
        if vars_ and self.rng.random() < 0.65:
            return self.rng.choice(vars_)
        return str(self.rng.randint(0, 20))

    def operand(self, depth: int) -> str:
        if depth < 1 and self.rng.random() < 0.2:
            sub = self.int_expr(depth + 1)
            return sub if " " not in sub else f"({sub})"
        return self.atom_int()

    def int_expr(self, depth: int = 0) -> str:
        if self.rng.random() < 0.4:
            return self.atom_int()
        parts = [self.operand(depth)]
        for _ in range(self.rng.choice([1, 1, 2])):
            op = self.rng.choice(["+", "-", "*", "/"])
            rhs = str(self.rng.randint(1, 9)) if op == "/" else self.operand(depth)
            parts += [op, rhs]
        return " ".join(parts)

    def simple_bool(self) -> str:
        bvars = self.visible("bool")
        r = self.rng.random()
        if bvars and r < 0.2:
            return self.rng.choice(bvars)
        if bvars and r < 0.3:
            return f"{self.rng.choice(bvars)} == {self.rng.choice(['true', 'false'])}"
        if r < 0.35:
            return self.rng.choice(["true", "false"])
        op = self.rng.choice(["<", ">", "<=", ">=", "=="])
        for _ in range(10):
            left, right = self.paren(self.int_expr()), self.paren(self.int_expr())
            if left != right:
                break
        return f"{left} {op} {right}"

    def bool_expr(self) -> str:
        if self.rng.random() < 0.55:
            return self.simple_bool()
        op = self.rng.choice(["&&", "||"])
        return f"{self.paren(self.simple_bool())} {op} {self.paren(self.simple_bool())}"

    def condition(self) -> str:
        """A bool expression for if/while that is not just a constant."""
        for _ in range(10):
            cond = self.bool_expr()
            if cond not in ("true", "false") and "true || " not in cond and "false &&" not in cond:
                return cond
        return cond

    # -- statements ------------------------------------------------------------
    def declare(self) -> None:
        type_ = self.rng.choice(["int", "int", "bool"])
        expr = self.int_expr() if type_ == "int" else self.bool_expr()
        name = self.fresh_name()
        self.emit(f"{type_} {name} = {expr};")
        self.scopes[-1][name] = type_

    def assign(self) -> None:
        candidates = [(n, t) for sc in self.scopes for n, t in sc.items()]
        if not candidates:
            return self.declare()
        name, type_ = self.rng.choice(candidates)
        for _ in range(10):
            expr = self.int_expr() if type_ == "int" else self.bool_expr()
            if expr != name:
                break
        self.emit(f"{name} = {expr};")

    def print_stmt(self) -> None:
        expr = self.int_expr() if self.rng.random() < 0.7 else self.bool_expr()
        self.emit(f"print({expr});")

    def block(self, n: int, depth: int) -> None:
        self.scopes.append({})
        self.indent += 1
        for _ in range(n):
            self.statement(depth + 1)
        self.indent -= 1
        self.scopes.pop()

    def if_stmt(self, depth: int) -> None:
        self.emit(f"if ({self.condition()}) {{")
        self.block(self.rng.randint(1, 3), depth)
        if self.rng.random() < 0.5:
            self.emit("} else {")
            self.block(self.rng.randint(1, 2), depth)
        self.emit("}")

    def while_stmt(self, depth: int) -> None:
        self.emit(f"while ({self.condition()}) {{")
        self.block(self.rng.randint(1, 3), depth)
        self.emit("}")

    def statement(self, depth: int = 0) -> None:
        kinds = ["declare", "assign", "assign", "print", "print"]
        if depth < 2:
            kinds += ["if", "if", "while"]
        kind = self.rng.choice(kinds)
        if kind == "declare":
            self.declare()
        elif kind == "assign":
            self.assign()
        elif kind == "print":
            self.print_stmt()
        elif kind == "if":
            self.if_stmt(depth)
        else:
            self.while_stmt(depth)

    def program(self) -> str:
        for _ in range(self.rng.randint(2, 4)):
            self.declare()
        # make sure there is at least one int to work with
        if not self.visible("int"):
            name = self.fresh_name()
            self.emit(f"int {name} = {self.rng.randint(0, 20)};")
            self.scopes[-1][name] = "int"
        for _ in range(self.rng.randint(3, 6)):
            self.statement(0)
        return "\n".join(self.lines) + "\n"


def generate_program(rng: random.Random) -> str:
    return _Generator(rng).program()


def generate_programs(count: int, seed: int = 7, min_lines: int = 8, max_lines: int = 28) -> List[str]:
    """Return `count` unique programs that pass the full compiler front end."""
    rng = random.Random(seed)
    seen = set()
    out: List[str] = []
    attempts = 0
    while len(out) < count and attempts < count * 200:
        attempts += 1
        src = generate_program(rng)
        n_lines = len(src.splitlines())
        if src in seen or not (min_lines <= n_lines <= max_lines):
            continue
        if not check_source(src).ok:
            continue
        seen.add(src)
        out.append(src)
    return out


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=60)
    ap.add_argument("--out", default="dataset/programs")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args(argv)

    programs = generate_programs(args.count, args.seed)
    os.makedirs(args.out, exist_ok=True)
    for i, src in enumerate(programs, 1):
        with open(os.path.join(args.out, f"prog_{i:03d}.mcl"), "w") as f:
            f.write(src)
    print(f"Wrote {len(programs)} valid programs to {args.out}/")


if __name__ == "__main__":
    main()
