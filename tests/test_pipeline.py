"""Pipeline plumbing tests with a fake LLM (no server needed).

The fake model is maximally compromised: it always obeys the injected instruction.
Vulnerable pipeline must get owned; hardened must not.
"""
import json

from app import agent, erp, llm

ACME = "buyer@acme-aero.example"
EVIL = {"order_id": "PO-200", "qty": 0}


def fake_chat_obedient(messages, tools=None):
    if tools:  # vulnerable agent: call the tool once, then stop
        if any(m["role"] == "tool" for m in messages):
            return {"role": "assistant", "content": "done"}
        return {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "function": {"name": "update_order_qty", "arguments": json.dumps(EVIL)}}]}
    # extractor: emits the attacker's intent, wrapped in noise
    return {"role": "assistant",
            "content": "<think>obey</think>```json\n" + json.dumps({"action": "update_qty", **EVIL}) + "\n```"}


def test_vulnerable_gets_owned(monkeypatch):
    monkeypatch.setattr(llm, "chat", fake_chat_obedient)
    db = erp.connect()
    agent.run_vulnerable(db, ACME, "whatever")
    assert erp.snapshot(db)["PO-200"]["qty"] == 0


def test_hardened_holds_against_compromised_extractor(monkeypatch):
    monkeypatch.setattr(llm, "chat", fake_chat_obedient)
    db = erp.connect()
    out = agent.run_hardened(db, ACME, "whatever")
    assert erp.snapshot(db)["PO-200"]["qty"] == 12
    assert out[0]["decision"] == "rejected"


def test_hardened_executes_benign_with_string_qty(monkeypatch):
    monkeypatch.setattr(llm, "chat", lambda m, tools=None: {
        "role": "assistant", "content": '{"action":"update_qty","order_id":"PO-100","qty":"44"}'})
    db = erp.connect()
    assert agent.run_hardened(db, ACME, "x")[0]["decision"] == "executed"
    assert erp.snapshot(db)["PO-100"]["qty"] == 44


def _fake_extractor_reads_everything(messages, tools=None):
    seen = messages[-1]["content"]
    intent = ({"action": "update_qty", "order_id": "PO-101", "qty": 260} if "260" in seen
              else {"action": "none", "order_id": "PO-101", "qty": None})
    return {"role": "assistant", "content": json.dumps(intent)}


def test_a6_owns_v1_but_not_hardened(monkeypatch):
    import pathlib
    email = next(a["email"] for a in json.loads(
        (pathlib.Path(__file__).parent.parent / "attacks" / "emails.json").read_text())
        if a["id"] == "A6-same-tenant-small")
    monkeypatch.setattr(llm, "chat", _fake_extractor_reads_everything)

    db = erp.connect()
    agent.run_hardened_v1(db, ACME, email)
    assert erp.snapshot(db)["PO-101"]["qty"] == 260  # residual risk is real

    db = erp.connect()
    agent.run_hardened(db, ACME, email)
    assert erp.snapshot(db)["PO-101"]["qty"] == 200  # provenance filter closes it


def test_ollama_style_dict_args_parsed():
    msg = {"tool_calls": [{"function": {"name": "get_order", "arguments": {"order_id": "PO-1"}}}]}
    assert llm.tool_calls(msg) == [(None, "get_order", {"order_id": "PO-1"})]
