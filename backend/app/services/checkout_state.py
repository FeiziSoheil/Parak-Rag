import json

REQUIRED_SLOTS = ("recipient_name", "phone", "address")
OPTIONAL_SLOTS = ("note",)
ALL_SLOTS = REQUIRED_SLOTS + OPTIONAL_SLOTS
PHASES = ("idle", "collecting", "awaiting_confirm")
NEXT_SLOTS = REQUIRED_SLOTS + ("note",)


def empty_state() -> dict:
    return {
        "phase": "idle",
        "recipient_name": None,
        "phone": None,
        "address": None,
        "note": None,
        "next_slot": None,
    }


def _clean_stored(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    return value or None


def load_checkout_state(raw: str | None) -> dict:
    state = empty_state()
    if raw is None or not str(raw).strip():
        return state
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return state
    if not isinstance(data, dict):
        return state
    phase = data.get("phase")
    state["phase"] = phase if phase in PHASES else "idle"
    for key in ALL_SLOTS:
        state[key] = _clean_stored(data.get(key))
    next_slot = data.get("next_slot")
    state["next_slot"] = next_slot if next_slot in NEXT_SLOTS else None
    return state


def dump_checkout_state(state: dict) -> str:
    payload = empty_state()
    payload.update({key: state.get(key) for key in payload})
    return json.dumps(payload, ensure_ascii=False)


def merge_slots(state: dict, slots: dict, *, allow_clear: bool) -> dict:
    out = dict(state)
    for key in ALL_SLOTS:
        if key not in slots or slots[key] is None:
            continue
        raw = slots[key]
        cleaned = raw.strip() if isinstance(raw, str) else str(raw).strip()
        if cleaned == "":
            if allow_clear:
                out[key] = None
            continue
        out[key] = cleaned
    return out


def advance_phase(state: dict) -> dict:
    out = dict(state)
    missing = next((key for key in REQUIRED_SLOTS if not out.get(key)), None)
    if missing:
        out["phase"] = "collecting"
        out["next_slot"] = missing
    else:
        out["phase"] = "awaiting_confirm"
        out["next_slot"] = None
    return out


def begin_collecting(state: dict) -> dict:
    return advance_phase(dict(state))


def fill_slots(state: dict, slots: dict) -> dict:
    merged = merge_slots(state, slots, allow_clear=state.get("phase") == "awaiting_confirm")
    return advance_phase(merged)


def ready_to_confirm(state: dict) -> bool:
    return state.get("phase") == "awaiting_confirm" and all(state.get(key) for key in REQUIRED_SLOTS)


def mark_idle() -> dict:
    return empty_state()


from sqlalchemy import text


def ensure_checkout_state_column(connection) -> None:
    rows = connection.execute(text("PRAGMA table_info(chat_sessions)"))
    cols = [row[1] for row in rows]
    if "checkout_state" not in cols:
        connection.execute(text("ALTER TABLE chat_sessions ADD COLUMN checkout_state TEXT"))
        connection.commit()
