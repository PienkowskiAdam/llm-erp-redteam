"""ERP tools exposed to the agent.

The vulnerable agent calls these directly with whatever the model decides.
The hardened pipeline calls them only after `policy.authorize`.
"""
import sqlite3


def get_order(db: sqlite3.Connection, order_id: str) -> dict | None:
    row = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    return dict(row) if row else None


def update_order_qty(db: sqlite3.Connection, order_id: str, qty: int) -> str:
    cur = db.execute("UPDATE orders SET qty = ? WHERE id = ?", (int(qty), order_id))
    db.execute("INSERT INTO audit(action, detail) VALUES ('qty', ?)", (f"{order_id}={qty}",))
    return "ok" if cur.rowcount else "not found"


def change_ship_address(db: sqlite3.Connection, order_id: str, address: str) -> str:
    cur = db.execute("UPDATE orders SET ship_address = ? WHERE id = ?", (address, order_id))
    db.execute("INSERT INTO audit(action, detail) VALUES ('addr', ?)", (f"{order_id}={address}",))
    return "ok" if cur.rowcount else "not found"


FUNCS = {
    "get_order": get_order,
    "update_order_qty": update_order_qty,
    "change_ship_address": change_ship_address,
}


def _fn(name: str, desc: str, props: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {"type": "object", "properties": props, "required": list(props)},
        },
    }


SCHEMAS = [
    _fn("get_order", "Read an order by id.", {"order_id": {"type": "string"}}),
    _fn("update_order_qty", "Set order quantity.",
        {"order_id": {"type": "string"}, "qty": {"type": "integer"}}),
    _fn("change_ship_address", "Change order shipping address.",
        {"order_id": {"type": "string"}, "address": {"type": "string"}}),
]
