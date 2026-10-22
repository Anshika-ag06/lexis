"""
mcl_corruption.py
------------------
Corruption engine - Phase 2 progress toward the AI diagnostic/repair
layer described in the Phase 1 report (Section 9.3) and this project's
own README roadmap.

Takes a *valid* MCL program and mechanically re-introduces exactly the
kinds of mistakes `mcl_parser.Parser` already knows how to recover from
(a missing ';', a missing ')'), plus a couple of purely lexical/operator
slips. Each corruption produces one labeled example:

    { original_source, corrupted_source, corruption_type, line_affected }

The parser and this corruption engine together act as a self-supervising
labeling oracle: nobody has to hand-annotate the "correct fix", because
the original, uncorrupted source already *is* the answer. This is the
dataset-generation half of Phase 2/3's planned LoRA fine-tuning pipeline
(Section 9.4 of the Phase 1 report) - the fine-tuning itself is still
future work, but the labeled data it will train on can already be
produced mechanically today.
"""

import json
import random
import re
from dataclasses import asdict, dataclass
from typing import List, Optional


@dataclass
class CorruptionExample:
    original: str
    corrupted: str
    corruption_type: str
    line_affected: int

    def to_dict(self):
        return asdict(self)


def _corrupt_missing_semicolon(lines: List[str], idx: int) -> Optional[str]:
    if lines[idx].rstrip().endswith(";"):
        stripped = lines[idx].rstrip()
        return stripped[:-1]
    return None


def _corrupt_missing_rparen(lines: List[str], idx: int) -> Optional[str]:
    pos = lines[idx].rfind(")")
    if pos == -1:
        return None
    return lines[idx][:pos] + lines[idx][pos + 1:]


def _corrupt_missing_lbrace(lines: List[str], idx: int) -> Optional[str]:
    if lines[idx].rstrip().endswith("{"):
        stripped = lines[idx].rstrip()
        return stripped[:-1].rstrip()
    return None


def _corrupt_operator_swap(lines: List[str], idx: int) -> Optional[str]:
    swaps = [("<=", "<"), (">=", ">"), ("==", "="), ("&&", "||")]
    for old, new in swaps:
        if old in lines[idx]:
            return lines[idx].replace(old, new, 1)
    return None


# A rule returns this to mean "remove the whole line" (a forgotten '}' leaves no
# blank line behind, so the dataset must not either).
DELETE_LINE = "\x00DELETE-LINE\x00"

KEYWORD_TYPOS = [
    ("while", "whlie"), ("print", "pritn"), ("else", "esle"),
    ("bool", "bol"), ("int", "itn"), ("if", "fi"),
]


def _corrupt_keyword_typo(lines: List[str], idx: int) -> Optional[str]:
    for kw, typo in KEYWORD_TYPOS:
        new, n = re.subn(rf"\b{kw}\b", typo, lines[idx], count=1)
        if n:
            return new
    return None


def _corrupt_extra_rparen(lines: List[str], idx: int) -> Optional[str]:
    pos = lines[idx].rfind(")")
    if pos == -1:
        return None
    return lines[idx][: pos + 1] + ")" + lines[idx][pos + 1:]


def _corrupt_missing_rbrace(lines: List[str], idx: int) -> Optional[str]:
    if lines[idx].strip() == "}":
        return DELETE_LINE
    return None


def _corrupt_missing_assign(lines: List[str], idx: int) -> Optional[str]:
    m = re.match(r"^(\s*(?:int|bool)\s+\w+)\s*=\s*(.+)$", lines[idx])
    if m:
        return f"{m.group(1)} {m.group(2)}"
    m = re.match(
        r"^(\s*(?!(?:if|while|print|else|int|bool)\b)[A-Za-z_]\w*)\s*=\s*(?!=)(.+)$", lines[idx]
    )
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return None


CORRUPTIONS = {
    "missing_semicolon": _corrupt_missing_semicolon,
    "missing_rparen": _corrupt_missing_rparen,
    "missing_lbrace": _corrupt_missing_lbrace,
    "operator_swap": _corrupt_operator_swap,
}

# Added in Phase 3 for the larger training set. Kept separate so the Review 2
# demo (`python mcl_corruption.py ...`) still uses exactly the original four.
EXTRA_CORRUPTIONS = {
    "keyword_typo": _corrupt_keyword_typo,
    "extra_rparen": _corrupt_extra_rparen,
    "missing_rbrace": _corrupt_missing_rbrace,
    "missing_assign": _corrupt_missing_assign,
}

ALL_CORRUPTIONS = {**CORRUPTIONS, **EXTRA_CORRUPTIONS}


def corrupt_program(source: str, rules: Optional[dict] = None) -> List[CorruptionExample]:
    """Return every single-line corruption of `source` that each
    corruption rule can produce - one example per (line, rule) hit.
    `rules` defaults to the original four rules (CORRUPTIONS)."""
    rules = CORRUPTIONS if rules is None else rules
    lines = source.splitlines()
    examples: List[CorruptionExample] = []
    for i in range(len(lines)):
        for kind, fn in rules.items():
            corrupted_line = fn(lines, i)
            if corrupted_line is None or corrupted_line == lines[i]:
                continue
            new_lines = lines.copy()
            new_lines[i] = corrupted_line
            examples.append(
                CorruptionExample(
                    original=source,
                    corrupted="\n".join(l for l in new_lines if l != DELETE_LINE),
                    corruption_type=kind,
                    line_affected=i + 1,
                )
            )
    return examples


def corrupt_multi(source: str, rng: random.Random, n: int = 2,
                  rules: Optional[dict] = None) -> Optional[CorruptionExample]:
    """Break `n` different lines of `source`, one random rule per line.
    Returns None if the program has fewer than `n` corruptible lines."""
    rules = ALL_CORRUPTIONS if rules is None else rules
    lines = source.splitlines()
    options = {}
    for i in range(len(lines)):
        for kind, fn in rules.items():
            new_line = fn(lines, i)
            if new_line is not None and new_line != lines[i]:
                options.setdefault(i, []).append((kind, new_line))
    if len(options) < n:
        return None
    chosen = sorted(rng.sample(sorted(options), n))
    new_lines = lines.copy()
    kinds = []
    for i in chosen:
        kind, new_line = rng.choice(options[i])
        new_lines[i] = new_line
        kinds.append(kind)
    return CorruptionExample(
        original=source,
        corrupted="\n".join(l for l in new_lines if l != DELETE_LINE),
        corruption_type="multi:" + "+".join(kinds),
        line_affected=chosen[0] + 1,
    )


def generate_dataset(programs: List[str], seed: Optional[int] = None) -> List[CorruptionExample]:
    """Corrupt every program in `programs` and return the pooled,
    shuffled list of examples - the synthetic training set."""
    all_examples: List[CorruptionExample] = []
    for src in programs:
        all_examples.extend(corrupt_program(src))
    if seed is not None:
        random.Random(seed).shuffle(all_examples)
    return all_examples


def dump_jsonl(examples: List[CorruptionExample], path: str) -> None:
    with open(path, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex.to_dict()) + "\n")


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python mcl_corruption.py <input.mcl> <output.jsonl>")
        sys.exit(1)
    with open(sys.argv[1]) as f:
        source = f.read()
    dataset = generate_dataset([source], seed=42)
    dump_jsonl(dataset, sys.argv[2])
    print(f"Generated {len(dataset)} corruption examples -> {sys.argv[2]}")
