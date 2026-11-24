"use client";

import { Package } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useOrders } from "@/contexts/OrdersContext";

export function OrdersHeaderButton() {
  const { open, setOpen } = useOrders();

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className="relative h-8 w-8"
      aria-label={open ? "Close orders" : "Open orders"}
      aria-pressed={open}
      onClick={() => setOpen(!open)}
    >
      <Package className="h-4 w-4" />
    </Button>
  );
}
