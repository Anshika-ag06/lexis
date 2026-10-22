import json, os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcl_check import check_source
from mcl_prompt import normalize_program
from mcl_rule_repair import edit_distance, rule_repair

GOOD = """int x = 5;
int y = 10;
if (x < y) {
    print(x);
} else {
    print(y);
}
while (x < y) {
    x = x + 1;
}"""


def broken(old, new):
    assert old in GOOD
    return GOOD.replace(old, new, 1)


@pytest.mark.parametrize("old,new", [
    ("int x = 5;", "int x = 5"),                      # missing ;
    ("if (x < y) {", "if (x < y {"),                  # missing )
    ("print(x);", "print(x));"),                       # extra )
    ("while (x < y) {", "while (x < y)"),             # missing {
    ("int y = 10;", "int y 10;"),                     # missing =
    ("while (x < y) {", "whlie (x < y) {"),           # keyword typo
    ("} else {", "} esle {"),                          # keyword typo after a brace
    ("    x = x + 1;\n}", "    x = x + 1;\n"),       # missing final }
])
def test_each_single_error_is_repaired_exactly(old, new):
    res = rule_repair(broken(old, new))
    assert res.status == "verified"
    assert normalize_program(res.repaired) == GOOD


def test_several_errors_are_repaired_in_one_run():
    src = broken("int x = 5;", "int x = 5").replace("print(y);", "print(y)")
    res = rule_repair(src)
    assert res.status == "verified"
    assert len(res.steps) >= 2


def test_equals_written_for_double_equals_is_fixed():
    res = rule_repair("int a = 3;\nbool b = a = 3;")
    assert res.status == "verified"
    assert "==" in res.repaired


def test_valid_program_is_returned_unchanged():
    res = rule_repair(GOOD)
    assert res.status == "already-valid" and res.repaired == GOOD


def test_semantic_problems_are_not_guessed_at():
    res = rule_repair("int x = y;")
    assert res.status == "unverified" and res.repaired == "int x = y;"


def test_unfixable_program_is_reported_unverified_and_terminates():
    res = rule_repair("@@@ ??? !!!")
    assert res.status == "unverified"


def test_repair_never_deletes_real_content():
    res = rule_repair(broken("int x = 5;", "int x = 5"))
    assert len(res.repaired.splitlines()) == len(GOOD.splitlines())


def test_edit_distance():
    assert edit_distance("while", "whlie") == 2
    assert edit_distance("int", "int") == 0
    assert edit_distance("bol", "bool") == 1


VAL = os.path.join(os.path.dirname(__file__), "..", "dataset", "out", "val.jsonl")


@pytest.mark.skipif(not os.path.exists(VAL), reason="dataset not built")
def test_rules_verify_most_of_the_validation_split():
    rows = [json.loads(l) for l in open(VAL)][:150]
    ok = sum(rule_repair(r["corrupted"]).status == "verified" for r in rows)
    assert ok / len(rows) >= 0.93
