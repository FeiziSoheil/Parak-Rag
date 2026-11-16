export function variantLabel(variant) {
  if (!variant) return "";
  const attrs = Array.isArray(variant.attributes) ? variant.attributes : [];
  const parts = attrs
    .map((attr) => {
      const name = (attr?.name || "").trim();
      const value = (attr?.value || "").trim();
      if (name && value) return `${name}: ${value}`;
      return value || name || "";
    })
    .filter(Boolean);
  if (parts.length) return parts.join(" · ");
  return (variant.name || variant.color || "").trim();
}

export function buildSidebarProduct(product, selectedVariant) {
  if (!product || product.product_id == null) return null;
  const label = selectedVariant ? variantLabel(selectedVariant) : "";
  const price =
    selectedVariant && selectedVariant.price != null ? selectedVariant.price : product.price ?? null;
  const variantImage = selectedVariant?.image && String(selectedVariant.image).trim();
  return {
    product_id: product.product_id,
    subject: product.subject || "",
    price,
    image_url: variantImage || product.image_url || null,
    category_name: product.category_name || "",
    variants: Array.isArray(product.variants) ? product.variants : [],
    selected_variant_label: label || null,
  };
}

export function commerceFollowUp(result) {
  const orderId = result && result.order && result.order.id != null ? result.order.id : null;
  return {
    refreshCart: Boolean(result && result.cart_updated),
    orderToast: orderId != null ? `Order #${orderId} placed` : null,
  };
}
