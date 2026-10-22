import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcl_repair import StubModel, repair, score_candidate

BROKEN = "int x = 5\nint y = 10;"
FIXED = "int x = 5;\nint y = 10;"


def test_already_valid_program_never_calls_the_model():
    model = StubModel(["whatever"])
    res = repair(FIXED, model)
    assert res.status == "already-valid" and model.calls == 0


def test_good_fix_is_verified_on_first_attempt():
    res = repair(BROKEN, StubModel([FIXED]))
    assert res.status == "verified" and res.attempts == 1
    assert res.repaired == FIXED


def test_fenced_model_output_is_unwrapped():
    res = repair(BROKEN, StubModel(["```mcl\n" + FIXED + "\n```"]))
    assert res.status == "verified"


def test_retry_succeeds_on_second_attempt_and_sees_new_diagnostics():
    model = StubModel(["int x = 5\nint y = 10", FIXED])      # first answer still broken
    res = repair(BROKEN, model, max_attempts=2)
    assert res.status == "verified" and res.attempts == 2
    assert "int y = 10" in model.prompts[1]                   # retry prompt built from the latest attempt


def test_unverified_when_model_never_produces_a_valid_program():
    model = StubModel([BROKEN])
    res = repair(BROKEN, model, max_attempts=2)
    assert res.status == "unverified" and res.attempts == 2 and model.calls == 2


def test_semantic_error_fix_is_checked_too():
    res = repair("int x = y;", StubModel(["int y = 1;\nint x = y;"]))
    assert res.status == "verified"


def test_score_candidate_distinguishes_verified_from_exact():
    valid_but_different = score_candidate("int a = 1;", FIXED)
    assert valid_but_different["verified"] and not valid_but_different["exact"]
    exact = score_candidate(FIXED + "\n", FIXED)
    assert exact["verified"] and exact["exact"]
    broken = score_candidate("int x = ;", FIXED)
    assert not broken["verified"] and not broken["exact"]
