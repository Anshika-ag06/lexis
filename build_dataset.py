"""
build_dataset.py
----------------
Turns a folder of valid MCL programs into the train / validation / test
JSONL files used to fine-tune and evaluate the repair model.

Pipeline
    1. Keep only programs that pass the full front end (the ground truth).
    2. Corrupt each one: every single-line corruption from every rule, plus
       randomly chosen two-error and three-error combinations.
    3. VERIFY each corrupted program with the real parser. An example is kept
       only if the parser actually reports a syntax error. (Some corruptions
       accidentally produce another valid program; those are dropped.)
    4. Attach the parser's structured diagnostics and build the model prompt.
    5. Split BY PROGRAM (not by example) so the test set contains programs the
       model has never seen in any form. Splitting by example would leak.

Usage:
    python build_dataset.py --programs dataset/programs --out dataset/out
"""

import argparse
import glob
import json
import os
import random
from collections import Counter, defaultdict
from typing import Dict, List, Optional

from mcl_check import check_source
from mcl_corruption import ALL_CORRUPTIONS, corrupt_multi, corrupt_program
from mcl_prompt import build_prompt, normalize_program


def load_programs(folder: str) -> List[tuple]:
    out = []
    for path in sorted(glob.glob(os.path.join(folder, "*.mcl"))):
        with open(path) as f:
            out.append((os.path.splitext(os.path.basename(path))[0], f.read()))
    return out


def split_programs(names: List[str], seed: int, val_frac: float, test_frac: float) -> Dict[str, str]:
    """Map each program name to 'train' / 'val' / 'test'."""
    names = sorted(names)
    random.Random(seed).shuffle(names)
    n = len(names)
    n_test = max(1, round(n * test_frac))
    n_val = max(1, round(n * val_frac))
    assignment = {}
    for i, name in enumerate(names):
        if i < n_test:
            assignment[name] = "test"
        elif i < n_test + n_val:
            assignment[name] = "val"
        else:
            assignment[name] = "train"
    return assignment


def build(programs_dir: str, out_dir: str, seed: int = 42, multi_per_program: int = 6,
          val_frac: float = 0.1, test_frac: float = 0.1) -> dict:
    programs = load_programs(programs_dir)
    valid, rejected_programs = [], []
    for name, src in programs:
        (valid if check_source(src).ok else rejected_programs).append((name, normalize_program(src)))
    if len(valid) < 3:
        raise SystemExit(f"Need at least 3 valid programs, found {len(valid)} in {programs_dir}")

    assignment = split_programs([n for n, _ in valid], seed, val_frac, test_frac)
    rng = random.Random(seed)

    attempted: Counter = Counter()
    accepted: Counter = Counter()
    splits: Dict[str, List[dict]] = {"train": [], "val": [], "test": []}
    seen = set()

    for name, original in valid:
        candidates = corrupt_program(original, rules=ALL_CORRUPTIONS)
        for k in range(multi_per_program):
            ex = corrupt_multi(original, rng, n=2 if k % 2 == 0 else 3)
            if ex is not None:
                candidates.append(ex)

        for ex in candidates:
            kind = "multi" if ex.corruption_type.startswith("multi:") else ex.corruption_type
            attempted[kind] += 1
            corrupted = normalize_program(ex.corrupted)
            if corrupted == original or (name, corrupted) in seen:
                continue
            result = check_source(corrupted)
            # keep only programs the PARSER rejects (lexical errors are fatal
            # in this compiler and carry no recovery record, so skip them too)
            if result.lex_error is not None or not result.syntax_errors:
                continue
            seen.add((name, corrupted))
            accepted[kind] += 1
            diagnostics = result.diagnostics()
            splits[assignment[name]].append({
                "id": f"{name}-{len(seen):05d}",
                "program": name,
                "corruption_type": ex.corruption_type,
                "line_affected": ex.line_affected,
                "diagnostics": diagnostics,
                "corrupted": corrupted,
                "prompt": build_prompt(corrupted, diagnostics),
                "completion": original,
            })

    os.makedirs(out_dir, exist_ok=True)
    for split, rows in splits.items():
        rng.shuffle(rows)
        with open(os.path.join(out_dir, f"{split}.jsonl"), "w") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    per_split_types = {
        split: dict(Counter(("multi" if r["corruption_type"].startswith("multi:") else r["corruption_type"])
                            for r in rows))
        for split, rows in splits.items()
    }
    programs_per_split = Counter(assignment.values())
    stats = {
        "programs_found": len(programs),
        "programs_valid": len(valid),
        "programs_rejected": [n for n, _ in rejected_programs],
        "programs_per_split": dict(programs_per_split),
        "examples_per_split": {k: len(v) for k, v in splits.items()},
        "examples_total": sum(len(v) for v in splits.values()),
        "examples_per_type_per_split": per_split_types,
        "corruptions_attempted_per_type": dict(attempted),
        "corruptions_accepted_per_type": dict(accepted),
        "acceptance_rate_per_type": {
            k: round(accepted[k] / attempted[k], 3) for k in attempted if attempted[k]
        },
        "max_prompt_chars": max((len(r["prompt"]) for rows in splits.values() for r in rows), default=0),
        "seed": seed,
    }
    with open(os.path.join(out_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2)
    return stats


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--programs", default="dataset/programs")
    ap.add_argument("--out", default="dataset/out")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--multi-per-program", type=int, default=6)
    args = ap.parse_args(argv)

    stats = build(args.programs, args.out, args.seed, args.multi_per_program)
    print(f"Programs: {stats['programs_valid']} valid of {stats['programs_found']} "
          f"(split {stats['programs_per_split']})")
    print(f"Examples: {stats['examples_total']} total -> {stats['examples_per_split']}")
    print("Accepted / attempted corruptions by type:")
    for kind, att in sorted(stats["corruptions_attempted_per_type"].items()):
        acc = stats["corruptions_accepted_per_type"].get(kind, 0)
        print(f"  {kind:<18} {acc:>4} / {att:<4} ({acc / att:.0%})")
    print(f"Wrote train/val/test.jsonl and stats.json to {args.out}/")


if __name__ == "__main__":
    main()
