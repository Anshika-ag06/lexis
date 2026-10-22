import sys, os, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import mcl_corruption as mc
from mcl_check import check_source

SRC = open(os.path.join(os.path.dirname(__file__), "programs", "valid_basic.mcl")).read()


def test_default_rules_unchanged_for_review_demo():
    assert len(mc.corrupt_program(SRC)) == 15          # number shown on the Review 2 slide
    assert {e.corruption_type for e in mc.corrupt_program(SRC)} == {
        "missing_semicolon", "missing_rparen", "missing_lbrace"}


def test_extra_rules_add_new_corruption_types():
    types = {e.corruption_type for e in mc.corrupt_program(SRC, mc.ALL_CORRUPTIONS)}
    assert {"keyword_typo", "extra_rparen", "missing_rbrace", "missing_assign"} <= types


def test_individual_extra_rules():
    assert mc._corrupt_keyword_typo(["while (x < y) {"], 0) == "whlie (x < y) {"
    assert mc._corrupt_extra_rparen(["print(x);"], 0) == "print(x));"
    assert mc._corrupt_missing_rbrace(["    }"], 0) == mc.DELETE_LINE
    assert mc._corrupt_missing_rbrace(["} else {"], 0) is None
    assert mc._corrupt_missing_assign(["int x = 5;"], 0) == "int x 5;"
    assert mc._corrupt_missing_assign(["x = x + 1;"], 0) == "x x + 1;"
    assert mc._corrupt_missing_assign(["if (x == 1) {"], 0) is None


def test_multi_error_changes_several_lines_and_still_fails_parsing():
    ex = mc.corrupt_multi(SRC, random.Random(1), n=2)
    assert ex.corruption_type.startswith("multi:")
    changed = [a != b for a, b in zip(SRC.splitlines(), ex.corrupted.splitlines())]
    assert sum(changed) >= 2
    assert check_source(ex.corrupted).syntax_errors


def test_multi_returns_none_when_program_too_small():
    assert mc.corrupt_multi("print(1);", random.Random(0), n=3) is None


def test_missing_rbrace_removes_the_line_and_leaves_no_blank_line():
    ex = [e for e in mc.corrupt_program(SRC, mc.ALL_CORRUPTIONS) if e.corruption_type == "missing_rbrace"][0]
    assert len(ex.corrupted.splitlines()) == len(SRC.splitlines()) - 1
    assert "\x00" not in ex.corrupted
    assert ex.corrupted.count("}") == SRC.count("}") - 1
