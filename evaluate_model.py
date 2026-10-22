"""
evaluate_model.py
-----------------
Scores a repair model on the held-out test set (programs it never saw).

Two metrics (Section 9.6 of the Phase 1 report):
    verified rate - the fix passes the whole compiler front end
    exact rate    - the fix equals the original program exactly
(Several different programs can be valid, so "exact" is the stricter of the two.)

Run each method on the SAME test examples, then compare:
    python evaluate_model.py --backend rules  --label rules --limit 100 --out results/rules.json
    python evaluate_model.py --backend ollama --shots 0 --label zero-shot --limit 100 --out results/zero.json
    python evaluate_model.py --backend ollama --shots 3 --label few-shot  --limit 100 --out results/few.json
    python evaluate_model.py --backend hybrid --label hybrid --limit 100 --out results/hybrid.json
    python compare_results.py results/rules.json results/zero.json results/few.json results/hybrid.json

--attempts 2 additionally runs the self-validating loop (retry once with fresh
diagnostics) on the examples that failed their first try, and reports the
result as "verified_with_loop". Examples that already passed are not re-run.
"""

import argparse
import json
import os
import time
from collections import defaultdict

from mcl_repair import DEFAULT_BASE, HybridRepairModel, METHODS, make_model, repair, score_candidate


def group(corruption_type: str) -> str:
    return "multi" if corruption_type.startswith("multi:") else corruption_type


def summarize(records, key):
    n = len(records)
    return {
        "n": n,
        "rate": round(sum(1 for r in records if r[key]) / n, 4) if n else 0.0,
        "count": sum(1 for r in records if r[key]),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--test", default="dataset/out/test.jsonl")
    ap.add_argument("--backend", choices=METHODS, default="rules",
                    help="rules = no AI; ollama = local LLM; hybrid = rules then LLM; hf = Hugging Face model")
    ap.add_argument("--model", default=None, help="Ollama model name (default qwen2.5:3b)")
    ap.add_argument("--shots", type=int, default=3, help="worked examples for the LLM (0 = zero-shot)")
    ap.add_argument("--train", default="dataset/out/train.jsonl", help="where few-shot examples come from")
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--label", default="model")
    ap.add_argument("--out", default="results/result.json")
    ap.add_argument("--limit", type=int, default=0, help="evaluate only the first N test examples (0 = all)")
    ap.add_argument("--batch", type=int, default=0, help="0 = 8 for hf, 1 otherwise")
    ap.add_argument("--attempts", type=int, default=1, help="2 also runs the retry loop")
    args = ap.parse_args()

    with open(args.test) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    if args.limit:
        rows = rows[: args.limit]
    print(f"Evaluating '{args.label}' ({args.backend}) on {len(rows)} test examples")

    model = make_model(args.backend, args.model, args.shots, pool_path=args.train,
                       adapter=args.adapter, base=args.base)
    batch_size = args.batch or (8 if args.backend == "hf" else 1)
    start = time.time()
    records = []
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        outputs = model.batch_generate([r["prompt"] for r in batch])
        for row, raw in zip(batch, outputs):
            score = score_candidate(raw, row["completion"])
            records.append({
                "id": row["id"],
                "corruption_type": row["corruption_type"],
                "group": group(row["corruption_type"]),
                "verified": score["verified"],
                "syntax_ok": score["syntax_ok"],
                "exact": score["exact"],
                "output": raw,
            })
        print(f"  {min(i + batch_size, len(rows))}/{len(rows)} done")

    if args.attempts > 1:
        failed = [r for r in records if not r["verified"]]
        print(f"Running the retry loop on the {len(failed)} example(s) that failed the first try "
              f"(one at a time, so this is the slow part)...")
        by_id = {row["id"]: row for row in rows}
        for done, rec in enumerate(records, 1):
            if rec["verified"]:
                rec["verified_with_loop"] = True      # already passed on attempt 1, so the loop keeps it
                continue
            res = repair(by_id[rec["id"]]["corrupted"], model, max_attempts=args.attempts)
            rec["verified_with_loop"] = res.status in ("verified", "already-valid")
            print(f"  loop: {sum(1 for r in records[:done] if not r['verified'])}/{len(failed)} retried")

    by_group = defaultdict(list)
    for r in records:
        by_group[r["group"]].append(r)

    summary = {
        "label": args.label,
        "backend": args.backend,
        "model": args.model if args.backend in ("ollama", "hybrid") else None,
        "shots": args.shots if args.backend in ("ollama", "hybrid") else None,
        "adapter": args.adapter,
        "n": len(records),
        "minutes": round((time.time() - start) / 60, 1),
        "verified": summarize(records, "verified"),
        "syntax_ok": summarize(records, "syntax_ok"),
        "exact": summarize(records, "exact"),
        "by_type": {
            g: {"n": len(rs), "verified": summarize(rs, "verified")["rate"], "exact": summarize(rs, "exact")["rate"]}
            for g, rs in sorted(by_group.items())
        },
    }
    if args.attempts > 1:
        summary["verified_with_loop"] = summarize(records, "verified_with_loop")
    if isinstance(model, HybridRepairModel):
        summary["llm_calls"] = model.llm_calls      # how often the rules had to hand over to the LLM

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump({"summary": summary, "examples": records}, f, indent=2)

    print(f"\n=== {args.label} ===")
    print(f"verified: {summary['verified']['count']}/{summary['n']} = {summary['verified']['rate']:.1%}")
    print(f"exact:    {summary['exact']['count']}/{summary['n']} = {summary['exact']['rate']:.1%}")
    if args.attempts > 1:
        print(f"verified with loop: {summary['verified_with_loop']['rate']:.1%}")
    print(f"Saved to {args.out}")


if __name__ == "__main__":
    main()
