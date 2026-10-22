"""
mcl_llm.py
----------
Talks to a model running locally in Ollama, using only the Python standard
library (no extra packages to install).

Two repair methods use this client:
    zero-shot : the model sees only the instruction, the compiler diagnostics
                and the broken program.
    few-shot  : the same, plus a few worked examples (broken program -> fixed
                program) shown first as earlier turns of the conversation.

The worked examples are drawn ONLY from the training split of the dataset, so
a test example can never appear in its own prompt.

The model's answer is never trusted: it goes back through the compiler front
end in the fix loop (mcl_repair.repair) and only counts if it passes.
"""

import json
import random
import urllib.error
import urllib.request
from typing import Dict, List, Optional

DEFAULT_MODEL = "qwen2.5:3b"
DEFAULT_HOST = "http://localhost:11434"
SYSTEM_PROMPT = (
    "You repair broken programs written in MCL, a small imperative language with "
    "int and bool variables, if/else, while and print. "
    "Reply with the corrected program only, with no explanation and no code fences."
)


class OllamaError(RuntimeError):
    """Raised with a plain-language message when Ollama cannot answer."""


def group_of(corruption_type: str) -> str:
    return "multi" if corruption_type.startswith("multi:") else corruption_type


def pick_shots(pool: List[dict], k: int, seed: int = 0, max_chars: int = 1500) -> List[dict]:
    """Choose `k` worked examples, each of a different error type, preferring
    short ones so the prompt stays small. Deterministic for a given seed."""
    if k <= 0:
        return []
    rows = [r for r in pool if len(r["prompt"]) + len(r["completion"]) <= max_chars]
    random.Random(seed).shuffle(rows)
    chosen, seen = [], set()
    for r in rows:
        g = group_of(r["corruption_type"])
        if g not in seen:
            seen.add(g)
            chosen.append(r)
        if len(chosen) == k:
            break
    return chosen


class OllamaRepairModel:
    """Same interface as the other repair models: generate(prompt) -> text."""

    def __init__(self, model: str = DEFAULT_MODEL, host: str = DEFAULT_HOST, shots: int = 0,
                 shot_pool: Optional[List[dict]] = None, seed: int = 0,
                 num_predict: int = 640, timeout: int = 300):
        self.model = model
        self.host = host.rstrip("/")
        self.num_predict = num_predict
        self.timeout = timeout
        if shots and not shot_pool:
            raise OllamaError("Few-shot prompting needs a pool of training examples "
                              "(dataset/out/train.jsonl). Run build_dataset.py first.")
        self.shots = pick_shots(shot_pool or [], shots, seed)

    # ---------------------------------------------------------------- plumbing
    def _request(self, path: str, payload: Optional[dict] = None) -> dict:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            self.host + path, data=data, headers={"Content-Type": "application/json"},
            method="POST" if payload is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = json.loads(e.read().decode()).get("error", "")
            except Exception:
                pass
            if e.code == 404:
                raise OllamaError(f"Ollama does not have the model '{self.model}'. "
                                  f"Run:  ollama pull {self.model}   ({detail})") from None
            raise OllamaError(f"Ollama returned an error ({e.code}): {detail}") from None
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            raise OllamaError(f"Cannot reach Ollama at {self.host}. Open the Ollama app "
                              f"(or run `ollama serve` in a terminal) and try again. ({e})") from None

    def ensure_ready(self) -> None:
        """Fail early, with a helpful message, if Ollama or the model is missing."""
        tags = self._request("/api/tags")
        names = {m.get("name", "") for m in tags.get("models", [])}
        if self.model not in names and f"{self.model}:latest" not in names:
            installed = ", ".join(sorted(names)) or "none"
            raise OllamaError(f"Model '{self.model}' is not installed. Installed: {installed}. "
                              f"Run:  ollama pull {self.model}")

    # -------------------------------------------------------------------- chat
    def messages_for(self, prompt: str) -> List[Dict[str, str]]:
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
        for ex in self.shots:
            msgs.append({"role": "user", "content": ex["prompt"]})
            msgs.append({"role": "assistant", "content": ex["completion"]})
        msgs.append({"role": "user", "content": prompt})
        return msgs

    def generate(self, prompt: str) -> str:
        reply = self._request("/api/chat", {
            "model": self.model,
            "messages": self.messages_for(prompt),
            "stream": False,
            "keep_alive": "15m",
            "options": {"temperature": 0, "seed": 0, "num_predict": self.num_predict},
        })
        try:
            return reply["message"]["content"]
        except (KeyError, TypeError):
            raise OllamaError(f"Unexpected reply from Ollama: {str(reply)[:200]}") from None

    def batch_generate(self, prompts: List[str]) -> List[str]:
        return [self.generate(p) for p in prompts]
