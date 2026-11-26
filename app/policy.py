"""Deterministic authorization layer. No LLM involved.

The model may only *propose* an intent; this code decides.
"""
import sqlite3
from dataclasses import dataclass

MAX_QTY_CHANGE_RATIO = 0.5  # >50% change needs a human


@dataclass
class Decision:
    allowed: bool
    needs_human: bool
    reason: str


def sender_domain(sender: str) -> str:
    return sender.rsplit("@", 1)[-1].strip().lower()


def authorize(db: sqlite3.Connection, sender: str, intent: dict) -> Decision:
    action = intent.get("action")
    if action not in {"none", "update_qty", "change_address"}:
        return Decision(False, False, f"unknown action {action!r}")
    if action == "none":
        return Decision(False, False, "no change requested")

    order = db.execute(
        "SELECT o.*, c.email_domain FROM orders o JOIN customers c ON c.id = o.customer_id WHERE o.id = ?",
        (str(intent.get("order_id")),),
    ).fetchone()
    if not order:
        return Decision(False, False, "order not found")

    # Identity comes from the transport (SMTP envelope / DKIM), never from email body or model output.
    # ponytail: domain match only; real deployment needs DKIM/SPF verification + per-contact allowlist.
    if sender_domain(sender) != order["email_domain"]:
        return Decision(False, False, "sender does not own order")

    if action == "update_qty":
        qty = intent.get("qty")
        if not isinstance(qty, int) or qty <= 0:
            return Decision(False, False, "invalid qty")
        if abs(qty - order["qty"]) > order["qty"] * MAX_QTY_CHANGE_RATIO:
            return Decision(False, True, "large qty change -> human approval")
        return Decision(True, False, "ok")

    # Address changes are a classic fraud vector (redirect shipment): always human.
    return Decision(False, True, "address change -> human approval")
