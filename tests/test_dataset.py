import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from build_dataset import build, split_programs
from mcl_check import check_source
from mcl_program_gen import generate_programs


def read(path):
    with open(path) as f:
        return [json.loads(line) for line in f]


def make_dataset(tmp_path):
    progs = tmp_path / "programs"
    progs.mkdir()
    for i, src in enumerate(generate_programs(12, seed=11), 1):
        (progs / f"p{i:02d}.mcl").write_text(src)
    out = tmp_path / "out"
    stats = build(str(progs), str(out), seed=1, multi_per_program=2)
    return out, stats


def test_split_is_by_program_with_no_overlap(tmp_path):
    out, _ = make_dataset(tmp_path)
    programs = {s: {r["program"] for r in read(out / f"{s}.jsonl")} for s in ("train", "val", "test")}
    assert programs["train"].isdisjoint(programs["val"])
    assert programs["train"].isdisjoint(programs["test"])
    assert programs["val"].isdisjoint(programs["test"])
    assert all(programs[s] for s in programs)


def test_every_example_is_verified_by_the_parser(tmp_path):
    out, _ = make_dataset(tmp_path)
    for split in ("train", "val", "test"):
        for row in read(out / f"{split}.jsonl"):
            assert check_source(row["completion"]).ok            # the answer is valid
            res = check_source(row["corrupted"])
            assert res.syntax_errors and res.lex_error is None   # the input really fails
            assert row["corrupted"] != row["completion"]
            assert row["diagnostics"] and row["prompt"].endswith("\n")


def test_stats_file_reports_acceptance_rates(tmp_path):
    out, stats = make_dataset(tmp_path)
    assert stats["examples_total"] == sum(stats["examples_per_split"].values())
    assert 0 < stats["acceptance_rate_per_type"]["operator_swap"] < 1   # some swaps stay valid and are dropped
    assert (out / "stats.json").exists()


def test_split_programs_is_deterministic_and_complete():
    names = [f"p{i}" for i in range(20)]
    a = split_programs(names, seed=3, val_frac=0.1, test_frac=0.1)
    assert a == split_programs(names, seed=3, val_frac=0.1, test_frac=0.1)
    assert sorted(a) == sorted(names)
    assert list(a.values()).count("test") == 2 and list(a.values()).count("val") == 2
