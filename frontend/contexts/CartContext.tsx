"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { toast } from "sonner";
import {
  addCartItem,
  createOrder,
  deleteCartItem,
  getCart,
  updateCartItem,
  type Cart,
  type CartItemCreateInput,
  type OrderCreateInput,
} from "@/lib/api";
import { isAuthenticated } from "@/lib/auth";

type CartContextValue = {
  cart: Cart | null;
  loading: boolean;
  open: boolean;
  setOpen: (open: boolean) => void;
  refresh: () => Promise<void>;
  addItem: (input: CartItemCreateInput) => Promise<void>;
  setQuantity: (itemId: number, quantity: number) => Promise<void>;
  removeItem: (itemId: number) => Promise<void>;
  checkout: (body: OrderCreateInput) => Promise<void>;
};

const CartContext = createContext<CartContextValue | null>(null);

const EMPTY: Cart = { items: [], item_count: 0, subtotal: null, checkout_ready: false };

export function CartProvider({ children }: { children: ReactNode }) {
  const [cart, setCart] = useState<Cart | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);

  const refresh = useCallback(async () => {
    if (!isAuthenticated()) {
      setCart(EMPTY);
      setLoading(false);
      return;
    }
    try {
      const data = await getCart();
      setCart(data);
    } catch {
      setCart(EMPTY);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const addItem = useCallback(
    async (input: CartItemCreateInput) => {
      try {
        await addCartItem(input);
        await refresh();
        toast.success("Added to cart");
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Failed to add to cart");
        throw e;
      }
    },
    [refresh]
  );

  const setQuantity = useCallback(
    async (itemId: number, quantity: number) => {
      try {
        await updateCartItem(itemId, quantity);
        await refresh();
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Failed to update cart");
        throw e;
      }
    },
    [refresh]
  );

  const removeItem = useCallback(
    async (itemId: number) => {
      try {
        await deleteCartItem(itemId);
        await refresh();
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Failed to remove item");
        throw e;
      }
    },
    [refresh]
  );

  const checkout = useCallback(
    async (body: OrderCreateInput) => {
      try {
        await createOrder(body);
        await refresh();
        toast.success("Order placed");
        setOpen(false);
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Checkout failed");
        throw e;
      }
    },
    [refresh]
  );

  return (
    <CartContext.Provider
      value={{
        cart,
        loading,
        open,
        setOpen,
        refresh,
        addItem,
        setQuantity,
        removeItem,
        checkout,
      }}
    >
      {children}
    </CartContext.Provider>
  );
}

export function useCart(): CartContextValue {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart must be used within CartProvider");
  return ctx;
}
