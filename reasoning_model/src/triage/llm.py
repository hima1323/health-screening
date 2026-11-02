"""Local Ollama chat with a JSON schema (temperature 0). Local only: the URL must point to this machine.

    python -m triage.llm            check that the local model answers, and how fast
"""
import json
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

import yaml

from triage.evidence import CONFIG

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def load_llm_config(path=CONFIG / "llm.yaml"):
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    if urlparse(cfg["url"]).hostname not in LOCAL_HOSTS:
        raise ValueError(f"llm.yaml url must be a local Ollama server, got {cfg['url']}")
    return cfg


class LLMError(RuntimeError):
    pass


def chat_json(system, user, schema, llm=None, timeout=None):
    """-> (parsed JSON dict, seconds). Raises LLMError on timeout, connection failure or unparseable output."""
    llm = llm or load_llm_config()
    body = {"model": llm["model"], "stream": False, "format": schema, "keep_alive": "30m",
            "options": {"temperature": 0, "seed": 0},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(llm["url"], json.dumps(body).encode(), {"Content-Type": "application/json"})
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout or llm["timeout_s"]) as r:
            content = json.loads(r.read())["message"]["content"]
        return json.loads(content), time.perf_counter() - t
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise LLMError(f"local LLM unavailable or too slow: {e}") from e
    except (ValueError, KeyError, TypeError) as e:
        raise LLMError(f"local LLM returned unparseable output: {e}") from e


def available(llm=None):
    llm = llm or load_llm_config()
    try:
        chat_json("Reply with JSON.", "Say ok.", {"type": "object", "properties": {"ok": {"type": "string"}}},
                  llm, timeout=llm["warmup_timeout_s"])
        return True
    except LLMError:
        return False


if __name__ == "__main__":
    llm = load_llm_config()
    t = time.perf_counter()
    print(f"{llm['model']} at {llm['url']}: {'ok' if available(llm) else 'NOT available'} "
          f"({time.perf_counter() - t:.1f} s incl. loading)")
