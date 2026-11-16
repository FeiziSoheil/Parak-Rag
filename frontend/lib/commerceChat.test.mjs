import assert from "node:assert/strict";
import test from "node:test";
import { buildSidebarProduct, commerceFollowUp, variantLabel } from "./commerceChat.mjs";

test("variant label uses attributes", () => {
  assert.equal(
    variantLabel({ attributes: [{ name: "Color", value: "Blue" }] }),
    "Color: Blue"
  );
});

test("sidebar snapshot keeps the selected variant price and image", () => {
  const snap = buildSidebarProduct(
    {
      product_id: 202,
      subject: "Shirt",
      price: 20,
      image_url: null,
      category_name: "Clothes",
      variants: [{ price: 22, image: "https://example.com/blue.jpg" }],
    },
    {
      price: 22,
      image: "https://example.com/blue.jpg",
      attributes: [{ name: "Color", value: "Blue" }],
    }
  );
  assert.equal(snap.selected_variant_label, "Color: Blue");
  assert.equal(snap.price, 22);
  assert.equal(snap.image_url, "https://example.com/blue.jpg");
  assert.equal(snap.product_id, 202);
});

test("missing product and missing variant", () => {
  assert.equal(buildSidebarProduct(null, null), null);
  const snap = buildSidebarProduct(
    { product_id: 1, subject: "Mug", price: 12.5, image_url: "https://example.com/m.jpg", category_name: "Home" },
    null
  );
  assert.equal(snap.selected_variant_label, null);
  assert.equal(snap.price, 12.5);
});

test("commerce follow-up refreshes and toasts only when the server says so", () => {
  assert.deepEqual(commerceFollowUp({ cart_updated: true, order: null }), {
    refreshCart: true,
    orderToast: null,
  });
  assert.deepEqual(commerceFollowUp({ cart_updated: true, order: { id: 9, total_amount: 12.5, status: "pending" } }), {
    refreshCart: true,
    orderToast: "Order #9 placed",
  });
  assert.deepEqual(commerceFollowUp({ cart_updated: false }), {
    refreshCart: false,
    orderToast: null,
  });
});
