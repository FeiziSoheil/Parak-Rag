from app.services.checkout_state import (
    advance_phase,
    begin_collecting,
    dump_checkout_state,
    empty_state,
    fill_slots,
    load_checkout_state,
    mark_idle,
    ready_to_confirm,
)


def test_empty_and_invalid_are_idle():
    idle = empty_state()
    assert idle == {
        "phase": "idle",
        "recipient_name": None,
        "phone": None,
        "address": None,
        "note": None,
        "next_slot": None,
    }
    assert load_checkout_state(None) == idle
    assert load_checkout_state("") == idle
    assert load_checkout_state("not-json") == idle
    assert load_checkout_state("[]") == idle


def test_load_keeps_valid_fields_and_drops_bad_phase():
    raw = dump_checkout_state(
        {
            "phase": "collecting",
            "recipient_name": "  Ada  ",
            "phone": "",
            "address": None,
            "note": " door ",
            "next_slot": "phone",
        }
    )
    loaded = load_checkout_state(raw)
    assert loaded["phase"] == "collecting"
    assert loaded["recipient_name"] == "Ada"
    assert loaded["phone"] is None
    assert loaded["note"] == "door"
    assert loaded["next_slot"] == "phone"
    assert load_checkout_state('{"phase":"nope"}')["phase"] == "idle"


def test_begin_collecting_asks_name_then_summary_when_complete():
    started = begin_collecting(empty_state())
    assert started["phase"] == "collecting"
    assert started["next_slot"] == "recipient_name"
    complete = {
        **empty_state(),
        "recipient_name": "Ada",
        "phone": "+98912",
        "address": "Tehran",
    }
    done = begin_collecting(complete)
    assert done["phase"] == "awaiting_confirm"
    assert done["next_slot"] is None
    assert ready_to_confirm(done) is True
    assert ready_to_confirm(started) is False


def test_fill_slots_walks_required_fields_and_note_is_optional():
    named = fill_slots(empty_state(), {"recipient_name": "Ada", "phone": None, "note": None})
    assert named["phase"] == "collecting"
    assert named["recipient_name"] == "Ada"
    assert named["next_slot"] == "phone"
    ready = fill_slots(
        named,
        {"phone": "+98912", "address": "Tehran", "note": "Leave at door"},
    )
    assert ready["phase"] == "awaiting_confirm"
    assert ready["note"] == "Leave at door"
    assert ready["next_slot"] is None


def test_clear_is_ignored_until_awaiting_confirm():
    collecting = fill_slots(empty_state(), {"recipient_name": "Ada"})
    kept = fill_slots(collecting, {"recipient_name": ""})
    assert kept["recipient_name"] == "Ada"
    waiting = fill_slots(collecting, {"phone": "+1", "address": "Tehran"})
    cleared = fill_slots(waiting, {"phone": ""})
    assert cleared["phase"] == "collecting"
    assert cleared["phone"] is None
    assert cleared["next_slot"] == "phone"
    assert ready_to_confirm(cleared) is False


def test_mark_idle_drops_draft():
    waiting = fill_slots(
        empty_state(),
        {"recipient_name": "Ada", "phone": "+1", "address": "Tehran"},
    )
    assert mark_idle() == empty_state()
    assert waiting["recipient_name"] == "Ada"


def test_advance_phase_never_blocks_on_note():
    state = advance_phase(
        {
            **empty_state(),
            "recipient_name": "Ada",
            "phone": "+1",
            "address": "Tehran",
            "note": None,
        }
    )
    assert state["phase"] == "awaiting_confirm"
    assert state["next_slot"] is None
