from app.services.commerce_actions import detect_commerce_action


def test_blank_message_is_none():
    assert detect_commerce_action("  ", "collecting", complete=lambda prompt: '{"action":"cart_add"}')["action"] == "none"


def test_parse_cart_add_json():
    def complete(prompt: str) -> str:
        assert "add two" in prompt
        return '{"action":"cart_add","quantity":2,"product_ref":{"hint":null,"product_id":null,"variant_label":null},"slots":{},"confirm":false,"cancel":false}'

    action = detect_commerce_action("add two", "idle", complete=complete)
    assert action["action"] == "cart_add"
    assert action["quantity"] == 2


def test_garbage_json_is_none():
    action = detect_commerce_action("hello", "idle", complete=lambda prompt: "sure, I can help")
    assert action["action"] == "none"


def test_collecting_prompt_prefers_checkout_over_search():
    seen = {}

    def complete(prompt: str) -> str:
        seen["prompt"] = prompt
        return '{"action":"checkout_fill","slots":{"address":"Tehran, Valiasr"}}'

    action = detect_commerce_action("Tehran, Valiasr", "collecting", complete=complete)
    assert "collecting" in seen["prompt"]
    assert "Tehran, Valiasr" in seen["prompt"]
    assert "unless the user is clearly starting a new product search" in seen["prompt"]
    assert action["action"] == "checkout_fill"
    assert action["slots"]["address"] == "Tehran, Valiasr"
