import json, os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import evaluate_model
from mcl_check import check_source
from mcl_prompt import build_prompt, program_from_prompt
from mcl_repair import HybridRepairModel, RuleRepairModel, StubModel, make_model, repair
from test_llm import FakeOllama, make_pool

BROKEN = "int x = 5\nint y = 10;\nif (x < y {\n    print(x);\n}"
GOOD = "int x = 5;\nint y = 10;\nif (x < y) {\n    print(x);\n}"


def prompt_for(src):
    return build_prompt(src, check_source(src).diagnostics())


def test_program_from_prompt_inverts_build_prompt():
    assert program_from_prompt(prompt_for(BROKEN)) == BROKEN
    with pytest.raises(ValueError):
        program_from_prompt("no program here")


def test_rule_model_works_inside_the_verified_fix_loop():
    res = repair(BROKEN, RuleRepairModel())
    assert res.status == "verified" and res.repaired == GOOD


def test_hybrid_does_not_call_the_llm_when_the_rules_succeed():
    llm = StubModel(["should never be used"])
    h = HybridRepairModel(llm)
    assert check_source(h.generate(prompt_for(BROKEN))).ok
    assert llm.calls == 0 and h.llm_calls == 0


def test_hybrid_hands_over_to_the_llm_when_the_rules_fail():
    semantic_only = "int x = y;"                       # rules do not guess at semantic problems
    llm = StubModel(["int y = 1;\nint x = y;"])
    h = HybridRepairModel(llm)
    out = h.generate(prompt_for(semantic_only))
    assert out == "int y = 1;\nint x = y;" and llm.calls == 1 and h.llm_calls == 1


def test_make_model_builds_each_method():
    assert isinstance(make_model("rules"), RuleRepairModel)
    with pytest.raises(SystemExit):
        make_model("nonsense")


def test_make_model_reports_missing_ollama_model_clearly(tmp_path):
    fake = FakeOllama(installed=("tinyllama:latest",))
    pool = tmp_path / "train.jsonl"
    pool.write_text("\n".join(json.dumps(r) for r in make_pool()))
    try:
        with pytest.raises(SystemExit) as e:
            make_model("ollama", "qwen2.5:3b", 3, pool_path=str(pool), host=fake.host)
        assert "ollama pull qwen2.5:3b" in str(e.value) and "tinyllama" in str(e.value)
    finally:
        fake.close()


def test_make_model_ollama_works_end_to_end_against_the_fake_server(tmp_path):
    fake = FakeOllama(reply=GOOD)
    pool = tmp_path / "train.jsonl"
    pool.write_text("\n".join(json.dumps(r) for r in make_pool()))
    try:
        model = make_model("ollama", "qwen2.5:3b", 3, pool_path=str(pool), host=fake.host)
        res = repair(BROKEN, model)
        assert res.status == "verified" and len(fake.requests[-1]["messages"]) == 8   # system + 3 pairs + user
    finally:
        fake.close()
