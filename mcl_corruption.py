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


CORRUPTIONS = {
    "missing_semicolon": _corrupt_missing_semicolon,
    "missing_rparen": _corrupt_missing_rparen,
    "missing_lbrace": _corrupt_missing_lbrace,
    "operator_swap": _corrupt_operator_swap,
}


def corrupt_program(source: str) -> List[CorruptionExample]:
    """Return every single-line corruption of `source` that each
    corruption rule can produce - one example per (line, rule) hit."""
    lines = source.splitlines()
    examples: List[CorruptionExample] = []
    for i in range(len(lines)):
        for kind, fn in CORRUPTIONS.items():
            corrupted_line = fn(lines, i)
            if corrupted_line is None or corrupted_line == lines[i]:
                continue
            new_lines = lines.copy()
            new_lines[i] = corrupted_line
            examples.append(
                CorruptionExample(
                    original=source,
                    corrupted="\n".join(new_lines),
                    corruption_type=kind,
                    line_affected=i + 1,
                )
            )
    return examples


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
