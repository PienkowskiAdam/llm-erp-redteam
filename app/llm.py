"""Minimal LLM client (stdlib only). Two backends:

  LLM_BACKEND=ollama  (default)  -> {OLLAMA_URL}/api/chat
  LLM_BACKEND=openai             -> {OPENAI_BASE_URL}/chat/completions
                                    (LM Studio, vLLM, LiteLLM proxy, ...)

Callers stay backend-agnostic via chat / tool_calls / tool_result / json_from.
"""
import json
import os
import re
import urllib.request

BACKEND = os.environ.get("LLM_BACKEND", "ollama").lower()
if BACKEND == "lmstudio":
    BACKEND = "openai"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "http://localhost:1234/v1").rstrip("/")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "lm-studio")
MODEL = os.environ.get("MODEL", "qwen2.5:7b")
TEMPERATURE = float(os.environ.get("TEMPERATURE", "0.7"))
TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "180"))


def _post(url: str, body: dict, headers: dict | None = None) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.load(resp)


def chat(messages: list[dict], tools: list[dict] | None = None) -> dict:
    """Return assistant message in backend-native shape (append it to history as-is)."""
    if BACKEND == "openai":
        body = {"model": MODEL, "messages": messages, "temperature": TEMPERATURE}
        if tools:
            body["tools"] = tools
        out = _post(f"{OPENAI_BASE_URL}/chat/completions", body,
                    {"Authorization": f"Bearer {OPENAI_API_KEY}"})
        msg = out["choices"][0]["message"]
        msg.setdefault("content", "")
        if msg.get("content") is None:
            msg["content"] = ""
        return msg

    body = {"model": MODEL, "messages": messages, "stream": False,
            "options": {"temperature": TEMPERATURE}}
    if tools:
        body["tools"] = tools
    return _post(f"{OLLAMA_URL}/api/chat", body)["message"]


def tool_calls(msg: dict) -> list[tuple[str | None, str, dict]]:
    """[(call_id, name, args_dict)] — args normalized to dict for both backends."""
    calls = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function", {})
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError:
                args = {"_unparsed": args}
        calls.append((tc.get("id"), fn.get("name", ""), args))
    return calls


def tool_result(call_id: str | None, content: str) -> dict:
    m = {"role": "tool", "content": content}
    if call_id:
        m["tool_call_id"] = call_id
    return m


def json_from(text: str) -> dict:
    """Extract JSON object from model output (handles <think>, ``` fences, chatter)."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start:end + 1])
