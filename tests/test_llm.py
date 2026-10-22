import json, os, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcl_llm import OllamaError, OllamaRepairModel, SYSTEM_PROMPT, pick_shots


def make_pool():
    kinds = ["missing_semicolon", "missing_rparen", "keyword_typo", "multi:a+b", "missing_assign"]
    return [{"prompt": f"PROMPT-{i}", "completion": f"FIX-{i}", "corruption_type": kinds[i % 5]}
            for i in range(20)]


class FakeOllama:
    """A tiny local web server that behaves like Ollama's /api/tags and /api/chat."""

    def __init__(self, installed=("qwen2.5:3b",), reply="int x = 1;"):
        self.installed, self.reply, self.requests = list(installed), reply, []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self._send(200, {"models": [{"name": n} for n in outer.installed]})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append(body)
                if body["model"] not in outer.installed:
                    return self._send(404, {"error": f"model '{body['model']}' not found"})
                self._send(200, {"message": {"role": "assistant", "content": outer.reply}})

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.host = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def fake():
    f = FakeOllama()
    yield f
    f.close()


def test_pick_shots_gives_distinct_error_types_and_is_deterministic():
    a = pick_shots(make_pool(), 3, seed=1)
    assert len(a) == 3
    assert len({r["corruption_type"].split(":")[0] for r in a}) == 3
    assert a == pick_shots(make_pool(), 3, seed=1)
    assert pick_shots(make_pool(), 0) == []


def test_zero_shot_message_is_system_plus_user(fake):
    m = OllamaRepairModel("qwen2.5:3b", fake.host)
    msgs = m.messages_for("BROKEN")
    assert [x["role"] for x in msgs] == ["system", "user"]
    assert msgs[0]["content"] == SYSTEM_PROMPT and msgs[1]["content"] == "BROKEN"


def test_few_shot_messages_alternate_and_end_with_the_real_prompt(fake):
    m = OllamaRepairModel("qwen2.5:3b", fake.host, shots=3, shot_pool=make_pool())
    msgs = m.messages_for("BROKEN")
    assert [x["role"] for x in msgs] == ["system"] + ["user", "assistant"] * 3 + ["user"]
    assert msgs[-1]["content"] == "BROKEN"
    assert msgs[1]["content"].startswith("PROMPT-") and msgs[2]["content"].startswith("FIX-")


def test_few_shot_without_a_pool_is_a_clear_error(fake):
    with pytest.raises(OllamaError, match="train"):
        OllamaRepairModel("qwen2.5:3b", fake.host, shots=3, shot_pool=None)


def test_generate_sends_temperature_zero_and_returns_the_reply(fake):
    m = OllamaRepairModel("qwen2.5:3b", fake.host)
    assert m.generate("BROKEN") == "int x = 1;"
    sent = fake.requests[-1]
    assert sent["model"] == "qwen2.5:3b" and sent["stream"] is False
    assert sent["options"]["temperature"] == 0


def test_ensure_ready_passes_when_the_model_is_installed(fake):
    OllamaRepairModel("qwen2.5:3b", fake.host).ensure_ready()


def test_missing_model_message_says_how_to_install_it(fake):
    m = OllamaRepairModel("qwen2.5-coder:3b", fake.host)
    with pytest.raises(OllamaError, match="ollama pull qwen2.5-coder:3b"):
        m.ensure_ready()
    with pytest.raises(OllamaError, match="ollama pull"):
        m.generate("x")


def test_unreachable_ollama_message_says_to_open_the_app():
    m = OllamaRepairModel("qwen2.5:3b", "http://127.0.0.1:9", timeout=2)   # nothing listens on port 9
    with pytest.raises(OllamaError, match="Open the Ollama app"):
        m.generate("x")
