"""Policy tests: deterministic, no LLM needed.

Key property: even a fully compromised extractor (attacker controls intent JSON)
cannot cause unauthorized ERP writes.
"""
from app import erp, policy

ACME = "buyer@acme-aero.example"


def test_cross_tenant_write_denied():
    db = erp.connect()
    d = policy.authorize(db, ACME, {"action": "update_qty", "order_id": "PO-200", "qty": 0})
    assert not d.allowed and not d.needs_human


def test_lookalike_domain_denied():
    db = erp.connect()
    d = policy.authorize(db, "x@acme-aero-billing.example",
                         {"action": "update_qty", "order_id": "PO-100", "qty": 41})
    assert not d.allowed


def test_address_change_always_human():
    db = erp.connect()
    d = policy.authorize(db, ACME, {"action": "change_address", "order_id": "PO-100", "address": "x"})
    assert not d.allowed and d.needs_human


def test_large_qty_change_human():
    db = erp.connect()
    d = policy.authorize(db, ACME, {"action": "update_qty", "order_id": "PO-101", "qty": 20000})
    assert d.needs_human


def test_invalid_qty_rejected():
    db = erp.connect()
    for q in (0, -5, "44", None, 4.5):
        assert not policy.authorize(db, ACME, {"action": "update_qty", "order_id": "PO-100", "qty": q}).allowed


def test_unknown_action_rejected():
    db = erp.connect()
    assert not policy.authorize(db, ACME, {"action": "drop_table", "order_id": "PO-100"}).allowed


def test_benign_small_change_allowed():
    db = erp.connect()
    assert policy.authorize(db, ACME, {"action": "update_qty", "order_id": "PO-100", "qty": 44}).allowed


def test_sql_injection_in_order_id_harmless():
    db = erp.connect()
    d = policy.authorize(db, ACME, {"action": "update_qty", "order_id": "PO-100' OR '1'='1", "qty": 44})
    assert not d.allowed and d.reason == "order not found"
