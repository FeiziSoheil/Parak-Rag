"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useCart } from "@/contexts/CartContext";
import { getProductImageUrl } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

function LineImage({ url, alt }: { url: string | null; alt: string }) {
  const [src, setSrc] = useState(() => (url ? getProductImageUrl(url) || url : null));
  const [failed, setFailed] = useState(false);

  if (failed || !src) {
    return <div className="h-14 w-14 shrink-0 rounded-md bg-muted" />;
  }
  return (
    <img
      src={src}
      alt={alt}
      className="h-14 w-14 shrink-0 rounded-md object-cover border border-border"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
  );
}

export function CartSheet() {
  const { cart, open, setOpen, setQuantity, removeItem, checkout } = useCart();
  const [step, setStep] = useState<"cart" | "checkout">("cart");
  const [side, setSide] = useState<"left" | "right">("right");
  const [submitting, setSubmitting] = useState(false);
  const [recipientName, setRecipientName] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [note, setNote] = useState("");

  useEffect(() => {
    if (typeof document !== "undefined") {
      setSide(document.documentElement.dir === "rtl" ? "left" : "right");
    }
  }, [open]);

  useEffect(() => {
    if (!open) {
      setStep("cart");
      setSubmitting(false);
    }
  }, [open]);

  const items = cart?.items ?? [];
  const checkoutReady = cart?.checkout_ready === true;

  async function handleCheckoutSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!checkoutReady) {
      toast.error("Cart has items without price");
      return;
    }
    if (!recipientName.trim() || !phone.trim() || !address.trim()) {
      toast.error("Please fill name, phone, and address");
      return;
    }
    setSubmitting(true);
    try {
      await checkout({
        recipient_name: recipientName.trim(),
        phone: phone.trim(),
        address: address.trim(),
        note: note.trim() || null,
      });
      setRecipientName("");
      setPhone("");
      setAddress("");
      setNote("");
    } catch {
      // toast already shown in context
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent side={side} className="flex flex-col p-0 sm:max-w-md">
        <SheetHeader className="p-4 border-b border-border text-left space-y-1">
          <SheetTitle>{step === "cart" ? "Cart" : "Checkout"}</SheetTitle>
          <SheetDescription>
            {step === "cart"
              ? items.length
                ? `${cart?.item_count ?? 0} item(s)`
                : "Your cart is empty"
              : "Enter delivery details to place your order"}
          </SheetDescription>
        </SheetHeader>

        {step === "cart" ? (
          <>
            <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">
              {items.length === 0 ? (
                <p className="text-sm text-muted-foreground py-8 text-center">Your cart is empty</p>
              ) : (
                items.map((item) => (
                  <div key={item.id} className="flex gap-3 items-start border-b border-border pb-3 last:border-0">
                    <LineImage url={item.image_url} alt={item.subject.slice(0, 40)} />
                    <div className="min-w-0 flex-1 space-y-1">
                      <p className="text-sm font-medium leading-snug line-clamp-2">{item.subject}</p>
                      {item.variant_label ? (
                        <p className="text-xs text-muted-foreground">{item.variant_label}</p>
                      ) : null}
                      <p className="text-sm tabular-nums">
                        {item.unit_price != null ? `$${item.unit_price.toFixed(2)}` : "Price on request"}
                      </p>
                      <div className="flex items-center gap-2 pt-1">
                        <Button
                          type="button"
                          variant="outline"
                          size="icon"
                          className="h-7 w-7"
                          disabled={item.quantity <= 1}
                          onClick={() => void setQuantity(item.id, item.quantity - 1)}
                          aria-label="Decrease quantity"
                        >
                          −
                        </Button>
                        <span className="text-sm tabular-nums w-6 text-center">{item.quantity}</span>
                        <Button
                          type="button"
                          variant="outline"
                          size="icon"
                          className="h-7 w-7"
                          onClick={() => void setQuantity(item.id, item.quantity + 1)}
                          aria-label="Increase quantity"
                        >
                          +
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="ml-auto text-destructive"
                          onClick={() => void removeItem(item.id)}
                        >
                          Remove
                        </Button>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
            <SheetFooter className="p-4 border-t border-border flex-col gap-3 sm:flex-col">
              {items.length > 0 && (
                <div className="flex justify-between text-sm w-full">
                  <span className="text-muted-foreground">Subtotal</span>
                  <span className="font-medium tabular-nums">
                    {checkoutReady && cart?.subtotal != null
                      ? `$${cart.subtotal.toFixed(2)}`
                      : "—"}
                  </span>
                </div>
              )}
              {!checkoutReady && items.length > 0 && (
                <p className="text-xs text-muted-foreground w-full">
                  Checkout requires a price on every item.
                </p>
              )}
              <Button
                type="button"
                className="w-full"
                disabled={!checkoutReady}
                onClick={() => setStep("checkout")}
              >
                Checkout
              </Button>
            </SheetFooter>
          </>
        ) : (
          <form onSubmit={handleCheckoutSubmit} className="flex flex-col flex-1 min-h-0">
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="recipient_name">Recipient name</Label>
                <Input
                  id="recipient_name"
                  value={recipientName}
                  onChange={(e) => setRecipientName(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="phone">Phone</Label>
                <Input
                  id="phone"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="address">Address</Label>
                <Textarea
                  id="address"
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  required
                  rows={3}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="note">Note (optional)</Label>
                <Textarea
                  id="note"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  rows={2}
                />
              </div>
            </div>
            <SheetFooter className="p-4 border-t border-border flex-row gap-2 sm:flex-row">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setStep("cart")}>
                Back
              </Button>
              <Button type="submit" className="flex-1" disabled={submitting || !checkoutReady}>
                {submitting ? "Placing…" : "Place order"}
              </Button>
            </SheetFooter>
          </form>
        )}
      </SheetContent>
    </Sheet>
  );
}
