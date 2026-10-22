"""
compare_results.py
------------------
Side-by-side table of any number of evaluation runs. The first file is the
baseline that the "change" columns are measured against.

    python compare_results.py results/rules.json results/zero.json results/few.json results/hybrid.json

Writes comparison.md next to the last file and prints the same table.
"""

import json
import os
import sys


def load(path):
    with open(path) as f:
        return json.load(f)["summary"]


def pct(x):
    return f"{x:.1%}"


def main():
    if len(sys.argv) < 3:
        print("Usage: python compare_results.py <baseline.json> <other.json> [more.json ...]")
        sys.exit(1)
    runs = [load(p) for p in sys.argv[1:]]
    labels = [r["label"] for r in runs]
    base = runs[0]

    lines = ["| Metric | " + " | ".join(labels) + " |", "|---|" + "---|" * len(runs)]
    for name, key in [("Verified fix rate", "verified"), ("Exact-match rate", "exact"),
                      ("Syntax-valid output rate", "syntax_ok")]:
        cells = []
        for r in runs:
            cell = pct(r[key]["rate"])
            if r is not base:
                cell += f" ({(r[key]['rate'] - base[key]['rate']) * 100:+.1f})"
            cells.append(cell)
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    if all("verified_with_loop" in r for r in runs):
        lines.append("| Verified with retry loop | " + " | ".join(pct(r["verified_with_loop"]["rate"]) for r in runs) + " |")
    lines.append("| Examples scored | " + " | ".join(str(r["n"]) for r in runs) + " |")
    lines.append("| Minutes taken | " + " | ".join(str(r.get("minutes", "?")) for r in runs) + " |")
    for r in runs:
        if "llm_calls" in r:
            lines.append(f"\n{r['label']}: the rules handed over to the LLM on {r['llm_calls']} of {r['n']} examples.")

    lines += ["", "Verified rate by error type (exact-match rate in brackets):", "",
              "| Error type | n | " + " | ".join(labels) + " |", "|---|---|" + "---|" * len(runs)]
    for g in sorted(set().union(*[set(r["by_type"]) for r in runs])):
        n = max(r["by_type"].get(g, {"n": 0})["n"] for r in runs)
        cells = []
        for r in runs:
            t = r["by_type"].get(g)
            cells.append(f"{pct(t['verified'])} ({pct(t['exact'])})" if t else "-")
        lines.append(f"| {g} | {n} | " + " | ".join(cells) + " |")

    text = "\n".join(lines)
    print(text)
    out = os.path.join(os.path.dirname(sys.argv[-1]) or ".", "comparison.md")
    with open(out, "w") as f:
        f.write(text + "\n")
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
