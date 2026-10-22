import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcl_check import check_source
from mcl_prompt import (build_prompt, extract_program, format_diagnostics,
                        normalize_program, tokenize_for_training)


def test_valid_program_passes_check():
    assert check_source("int x = 5;\nprint(x);").ok


def test_syntax_error_is_reported_with_diagnostics():
    res = check_source("int x = 5\nint y = 10;")
    assert not res.ok
    assert len(res.syntax_errors) == 1
    assert res.diagnostics()[0]["expected_token"] == "';'"


def test_semantic_error_only_checked_when_syntax_is_clean():
    res = check_source("int x = y;")
    assert not res.syntax_errors
    assert [d["kind"] for d in res.diagnostics()] == ["undeclared"]


def test_lexical_error_is_captured_not_raised():
    res = check_source("int x = 12abc;")
    assert res.lex_error is not None
    assert not res.ok
    assert res.diagnostics()[0]["kind"] == "lexical"


def test_normalize_program():
    assert normalize_program("\n\nint x = 1;   \n\nprint(x);\n\n") == "int x = 1;\n\nprint(x);"


def test_prompt_contains_program_and_diagnostics_but_not_recovery_action():
    res = check_source("int x = 5\nint y = 10;")
    prompt = build_prompt(res.source, res.diagnostics())
    assert "int x = 5" in prompt
    assert "expected ';'" in prompt
    assert "inserted missing" not in prompt          # would leak the fix


def test_format_diagnostics_handles_semantic_records():
    text = format_diagnostics([{"kind": "undeclared", "message": "'y' is not declared", "line": 3, "column": 1}])
    assert "line 3" in text and "undeclared" in text


def test_extract_program_strips_code_fences():
    assert extract_program("```mcl\nint x = 1;\n```") == "int x = 1;"
    assert extract_program("Here you go:\n```\nint x = 1;\n```\nDone.") == "int x = 1;"
    assert extract_program("int x = 1;") == "int x = 1;"
    assert extract_program("```\nint x = 1;") == "int x = 1;"


class FakeTokenizer:
    eos_token = "<eos>"

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
        return "<u>" + messages[0]["content"] + "</u><a>"

    def __call__(self, text, add_special_tokens=False):
        return {"input_ids": [ord(c) for c in text]}


def test_training_labels_mask_the_prompt_and_train_on_completion():
    tok = FakeTokenizer()
    out = tokenize_for_training(tok, "PROMPT", "FIX")
    prompt_len = len("<u>PROMPT</u><a>")
    assert out["labels"][:prompt_len] == [-100] * prompt_len
    assert out["labels"][prompt_len:] == out["input_ids"][prompt_len:]
    assert "".join(chr(i) for i in out["labels"][prompt_len:]) == "FIX<eos>"


def test_training_truncates_to_max_len():
    out = tokenize_for_training(FakeTokenizer(), "P" * 50, "F" * 50, max_len=40)
    assert len(out["input_ids"]) == len(out["labels"]) == 40
