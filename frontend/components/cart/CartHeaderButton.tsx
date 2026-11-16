"use client";

import { ShoppingCart } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCart } from "@/contexts/CartContext";
import { CartSheet } from "./CartSheet";

export function CartHeaderButton() {
  const { cart, setOpen } = useCart();
  const count = cart?.item_count ?? 0;

  return (
    <>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="relative h-8 w-8"
        aria-label="Open cart"
        onClick={() => setOpen(true)}
      >
        <ShoppingCart className="h-4 w-4" />
        {count > 0 && (
          <span className="absolute -top-1 -right-1 min-w-4 h-4 px-1 rounded-full bg-primary text-primary-foreground text-[10px] leading-4 text-center">
            {count > 99 ? "99+" : count}
          </span>
        )}
      </Button>
      <CartSheet />
    </>
  );
}
