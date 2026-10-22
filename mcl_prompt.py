"""
mcl_prompt.py
-------------
The single definition of how a broken MCL program is shown to the repair
model, plus the small text helpers everything else shares.

Training, evaluation and the fix loop all import `build_prompt` from here.
If the training prompt and the inference prompt ever differ, a fine-tuned
model quietly performs worse, so there is deliberately only one copy.

Note: the prompt includes the compiler's diagnostics (line, column,
expected/found token) but NOT the parser's `recovery_action` text, because
that text names the exact repair and would leak the answer.
"""

import re
from typing import List

INSTRUCTION = (
    "You are a compiler assistant for MCL, a small imperative language. "
    "Fix the error(s) in the program below. "
    "Return only the corrected program, with no explanation."
)


def normalize_program(text: str) -> str:
    """Strip trailing spaces, leading/trailing blank lines. Used for both
    dataset text and for exact-match comparison."""
    lines = [ln.rstrip() for ln in text.strip("\n").splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def format_diagnostics(diagnostics: List[dict]) -> str:
    if not diagnostics:
        return "- (none reported)"
    out = []
    for d in diagnostics:
        if "expected_token" in d:
            out.append(
                f"- line {d['line']}, column {d['column']}: syntax error, "
                f"expected {d['expected_token']} but found {d['actual_token']!r}"
            )
        else:
            out.append(f"- line {d['line']}: {d.get('kind', 'error')} error: {d['message']}")
    return "\n".join(out)


def build_prompt(source: str, diagnostics: List[dict]) -> str:
    return (
        f"{INSTRUCTION}\n\n"
        f"Compiler diagnostics:\n{format_diagnostics(diagnostics)}\n\n"
        f"Program:\n{normalize_program(source)}\n"
    )


def program_from_prompt(prompt: str) -> str:
    """Inverse of build_prompt: the broken program a prompt contains."""
    marker = "\nProgram:\n"
    if marker not in prompt:
        raise ValueError("prompt does not contain a 'Program:' section")
    return normalize_program(prompt.split(marker, 1)[1])


_FENCE = re.compile(r"```[A-Za-z0-9_+-]*\n(.*?)```", re.DOTALL)


def extract_program(model_output: str) -> str:
    """Pull the program out of a model reply: take the first fenced code
    block if there is one, otherwise the whole reply."""
    m = _FENCE.search(model_output)
    if m:
        return normalize_program(m.group(1))
    text = model_output.strip()
    if text.startswith("```"):  # opening fence but no closing one
        text = text.split("\n", 1)[1] if "\n" in text else ""
    return normalize_program(text)


def chat_prompt_text(tokenizer, prompt: str) -> str:
    return tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True
    )


def tokenize_for_training(tokenizer, prompt: str, completion: str, max_len: int = 1024) -> dict:
    """Turn one (prompt, completion) pair into model inputs where only the
    completion tokens are trained on (prompt tokens get label -100)."""
    prompt_text = chat_prompt_text(tokenizer, prompt)
    full_text = prompt_text + completion + (getattr(tokenizer, "eos_token", "") or "")
    prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
    full_ids = tokenizer(full_text, add_special_tokens=False)["input_ids"][:max_len]
    n_prompt = min(len(prompt_ids), len(full_ids))
    labels = [-100] * n_prompt + full_ids[n_prompt:]
    return {
        "input_ids": full_ids,
        "attention_mask": [1] * len(full_ids),
        "labels": labels,
    }
