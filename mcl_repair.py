"""
mcl_repair.py
-------------
The self-validating fix loop (Section 9.5 of the Phase 1 report).

    1. Run the broken program through the compiler -> structured diagnostics.
    2. Ask a repair model for a corrected program.
    3. Run the model's answer through the SAME compiler front end.
    4. 0 errors  -> status "verified".
       otherwise -> feed the new diagnostics back and try again, up to
                    `max_attempts`; if it never passes, status "unverified".

"Verified" means the fix is accepted by the lexer, parser and semantic
analyzer. It does NOT prove the fix preserves the author's intent, which is
why exact-match against the original is measured separately in evaluation.

The "model" is any object with `generate(prompt) -> str`. Methods:
    rules   - RuleRepairModel: small edits near the error, no AI (mcl_rule_repair)
    ollama  - OllamaRepairModel: a local LLM, zero-shot or few-shot (mcl_llm)
    hybrid  - HybridRepairModel: rules first, the LLM only if the rules fail
    hf      - HFRepairModel: a Hugging Face model + optional LoRA adapter (needs
              torch; kept for the fine-tuning experiment in future_work/)
    StubModel is a scripted fake used by the unit tests.

Usage:
    python mcl_repair.py broken.mcl --method rules
    python mcl_repair.py broken.mcl --method ollama --model qwen2.5:3b --shots 3
"""

import argparse
import sys
from dataclasses import dataclass, field
from typing import List, Optional

import json
import os

from mcl_check import check_source
from mcl_prompt import (build_prompt, chat_prompt_text, extract_program, normalize_program,
                        program_from_prompt)
from mcl_rule_repair import rule_repair

DEFAULT_BASE = "Qwen/Qwen2.5-Coder-0.5B-Instruct"


# --------------------------------------------------------------------- models
class StubModel:
    """Returns pre-set replies in order (the last one repeats). For tests."""

    def __init__(self, replies: List[str]):
        self.replies = list(replies)
        self.calls = 0
        self.prompts: List[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        return reply


class RuleRepairModel:
    """Method A: no AI. Repairs the program found inside the prompt."""

    def generate(self, prompt: str) -> str:
        return rule_repair(program_from_prompt(prompt)).repaired

    def batch_generate(self, prompts: List[str]) -> List[str]:
        return [self.generate(p) for p in prompts]


class HybridRepairModel:
    """Method D: try the rules first and only ask the LLM when they fail.
    Cheap and fast, and the LLM is used just for what the rules cannot fix."""

    def __init__(self, llm):
        self.rules = RuleRepairModel()
        self.llm = llm
        self.llm_calls = 0

    def generate(self, prompt: str) -> str:
        attempt = self.rules.generate(prompt)
        if check_source(attempt).ok:
            return attempt
        self.llm_calls += 1
        return self.llm.generate(prompt)

    def batch_generate(self, prompts: List[str]) -> List[str]:
        return [self.generate(p) for p in prompts]


class HFRepairModel:
    """Base model, optionally with a LoRA adapter on top. Needs torch,
    transformers and (for an adapter) peft. Imports are lazy so the rest of
    the project works without them."""

    def __init__(self, base: str = DEFAULT_BASE, adapter: Optional[str] = None,
                 max_new_tokens: int = 640):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.max_new_tokens = max_new_tokens
        self.tokenizer = AutoTokenizer.from_pretrained(base)
        self.tokenizer.padding_side = "left"
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        dtype = torch.float16 if self.device == "cuda" else torch.float32
        model = AutoModelForCausalLM.from_pretrained(base, torch_dtype=dtype)
        if adapter:
            from peft import PeftModel
            model = PeftModel.from_pretrained(model, adapter)
        self.model = model.to(self.device).eval()

    def batch_generate(self, prompts: List[str]) -> List[str]:
        texts = [chat_prompt_text(self.tokenizer, p) for p in prompts]
        enc = self.tokenizer(texts, return_tensors="pt", padding=True, add_special_tokens=False)
        enc = {k: v.to(self.device) for k, v in enc.items()}
        with self.torch.no_grad():
            out = self.model.generate(
                **enc, max_new_tokens=self.max_new_tokens, do_sample=False,
                pad_token_id=self.tokenizer.pad_token_id,
            )
        new_tokens = out[:, enc["input_ids"].shape[1]:]
        return self.tokenizer.batch_decode(new_tokens, skip_special_tokens=True)

    def generate(self, prompt: str) -> str:
        return self.batch_generate([prompt])[0]


# ------------------------------------------------------------------- factory
METHODS = ("rules", "ollama", "hybrid", "hf")


def load_pool(path: str) -> List[dict]:
    if not os.path.exists(path):
        raise SystemExit(f"Training examples not found at {path}. Run build_dataset.py first.")
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def make_model(method: str, model: Optional[str] = None, shots: int = 3,
               pool_path: str = "dataset/out/train.jsonl", host: Optional[str] = None,
               adapter: Optional[str] = None, base: str = DEFAULT_BASE):
    """Build the repair model for a method name. For the LLM methods this also
    checks that Ollama is running and the model is installed."""
    if method == "rules":
        return RuleRepairModel()
    if method in ("ollama", "hybrid"):
        from mcl_llm import DEFAULT_HOST, DEFAULT_MODEL, OllamaError, OllamaRepairModel
        pool = load_pool(pool_path) if shots else None
        llm = OllamaRepairModel(model or DEFAULT_MODEL, host or DEFAULT_HOST, shots, pool)
        try:
            llm.ensure_ready()
        except OllamaError as e:
            raise SystemExit(f"\nProblem: {e}")
        return HybridRepairModel(llm) if method == "hybrid" else llm
    if method == "hf":
        return HFRepairModel(base, adapter)
    raise SystemExit(f"Unknown method '{method}'. Choose one of: {', '.join(METHODS)}")


# ------------------------------------------------------------------- scoring
def score_candidate(model_output: str, expected: str) -> dict:
    """Score one model reply against the known-correct program."""
    candidate = extract_program(model_output)
    result = check_source(candidate)
    return {
        "candidate": candidate,
        "verified": result.ok,
        "syntax_ok": result.lex_error is None and not result.syntax_errors,
        "exact": normalize_program(candidate) == normalize_program(expected),
        "error_count": result.error_count,
    }


# ------------------------------------------------------------------ the loop
@dataclass
class RepairResult:
    status: str                      # "already-valid" | "verified" | "unverified"
    original: str
    repaired: str
    attempts: int = 0
    history: List[dict] = field(default_factory=list)   # one entry per attempt


def repair(source: str, model, max_attempts: int = 2) -> RepairResult:
    current = normalize_program(source)
    first = check_source(current)
    if first.ok:
        return RepairResult("already-valid", current, current, attempts=0)

    result = RepairResult("unverified", current, current)
    check = first
    for attempt in range(1, max_attempts + 1):
        prompt = build_prompt(current, check.diagnostics())
        raw = model.generate(prompt)
        candidate = extract_program(raw)
        cand_check = check_source(candidate)
        result.attempts = attempt
        result.history.append({
            "attempt": attempt,
            "candidate": candidate,
            "verified": cand_check.ok,
            "error_count": cand_check.error_count,
        })
        result.repaired = candidate
        if cand_check.ok:
            result.status = "verified"
            return result
        current, check = candidate, cand_check   # retry from the latest attempt
    return result


# ----------------------------------------------------------------------- CLI
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Repair a broken MCL file and verify the result.")
    ap.add_argument("path")
    ap.add_argument("--method", choices=METHODS, default="rules")
    ap.add_argument("--model", default=None, help="Ollama model name (default qwen2.5:3b)")
    ap.add_argument("--shots", type=int, default=3, help="worked examples for the LLM (0 = zero-shot)")
    ap.add_argument("--adapter", default=None, help="LoRA adapter folder (method hf only)")
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--attempts", type=int, default=2)
    args = ap.parse_args(argv)

    with open(args.path) as f:
        source = f.read()
    model = make_model(args.method, args.model, args.shots, adapter=args.adapter, base=args.base)
    res = repair(source, model, args.attempts)
    print(f"Status: {res.status} (attempts used: {res.attempts})")
    if res.status != "already-valid":
        print("\n--- suggested program ---")
        print(res.repaired)
    return 0 if res.status in ("verified", "already-valid") else 1


if __name__ == "__main__":
    sys.exit(main())
