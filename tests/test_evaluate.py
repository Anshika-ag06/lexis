import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import evaluate_model
import compare_results
from build_dataset import build
from mcl_program_gen import generate_programs


class FakeModel:
    """Answers correctly for even-numbered prompts, returns junk otherwise."""
    def __init__(self, answers, good):
        self.answers, self.good, self.i = answers, good, 0

    def batch_generate(self, prompts):
        out = []
        for p in prompts:
            out.append(self.answers[p] if self.good else "I cannot help with that")
        return out

    def generate(self, prompt):
        return self.batch_generate([prompt])[0]


def run_eval(monkeypatch, tmp_path, test_file, rows, good, label):
    answers = {r["prompt"]: r["completion"] for r in rows}
    monkeypatch.setattr(evaluate_model, "make_model", lambda *a, **k: FakeModel(answers, good))
    out = tmp_path / f"{label}.json"
    monkeypatch.setattr(sys, "argv", ["evaluate_model.py", "--test", str(test_file), "--label", label,
                                      "--out", str(out), "--limit", "20", "--batch", "6", "--attempts", "2"])
    evaluate_model.main()
    return out


def test_evaluate_and_compare_end_to_end(monkeypatch, tmp_path):
    progs = tmp_path / "programs"
    progs.mkdir()
    for i, src in enumerate(generate_programs(10, seed=2), 1):
        (progs / f"p{i}.mcl").write_text(src)
    build(str(progs), str(tmp_path / "out"), seed=1, multi_per_program=2)
    test_file = tmp_path / "out" / "test.jsonl"
    rows = [json.loads(l) for l in open(test_file)][:20]

    good = run_eval(monkeypatch, tmp_path, test_file, rows, True, "good")
    bad = run_eval(monkeypatch, tmp_path, test_file, rows, False, "bad")

    g = json.load(open(good))["summary"]
    b = json.load(open(bad))["summary"]
    assert g["n"] == b["n"] == 20
    assert g["verified"]["rate"] == 1.0 and g["exact"]["rate"] == 1.0
    assert b["verified"]["rate"] == 0.0 and b["exact"]["rate"] == 0.0
    assert g["verified_with_loop"]["rate"] == 1.0
    assert sum(t["n"] for t in g["by_type"].values()) == 20

    monkeypatch.setattr(sys, "argv", ["compare_results.py", str(bad), str(good)])
    compare_results.main()
    assert (tmp_path / "comparison.md").exists()
    assert "(+100.0)" in (tmp_path / "comparison.md").read_text()
