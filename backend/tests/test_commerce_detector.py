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


def test_persian_order_second_is_checkout_without_llm():
    def complete(prompt: str) -> str:
        raise AssertionError("llm should not be required")

    action = detect_commerce_action("این دومی رو سفارش بده", "idle", complete=complete)
    assert action["action"] == "checkout_start"
    assert action["product_ref"]["hint"] == "second"
    assert action["confirm"] is False


def test_persian_add_first_with_size_is_cart_add():
    action = detect_commerce_action(
        "همین اولی رو با سایز ۴۰ به سبدم اضافه کن Men's Trail Shoe",
        "idle",
        complete=lambda prompt: '{"action":"none"}',
    )
    assert action["action"] == "cart_add"
    assert action["product_ref"]["hint"] == "first"
    assert action["product_ref"]["variant_label"] == "Size: 40"
    assert action["confirm"] is False


def test_english_order_the_second_one():
    action = detect_commerce_action(
        "order the second one",
        "idle",
        complete=lambda prompt: '{"action":"none"}',
    )
    assert action["action"] == "checkout_start"
    assert action["product_ref"]["hint"] == "second"


def test_add_the_blue_one_still_uses_llm():
    def complete(prompt: str) -> str:
        return '{"action":"cart_add","product_ref":{"hint":"blue","variant_label":null}}'

    action = detect_commerce_action("add the blue one", "idle", complete=complete)
    assert action["action"] == "cart_add"
    assert action["product_ref"]["hint"] == "blue"


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
