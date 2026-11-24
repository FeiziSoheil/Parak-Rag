"use client";

import { useEffect, useState } from "react";
import { useOrders } from "@/contexts/OrdersContext";
import { getProductImageUrl, type Order } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const ORDERS_WIDTH_PX = 320;
/** Match main floating sidebar + cart: duration-200 ease-linear */
const ORDERS_MOTION_MS = 200;

const STATUS_LABELS: Record<string, string> = {
  pending: "Pending",
  paid: "Paid",
  shipped: "Shipped",
  delivered: "Delivered",
  cancelled: "Cancelled",
};

function LineImage({ url, alt }: { url: string | null; alt: string }) {
  const [src] = useState(() => (url ? getProductImageUrl(url) || url : null));
  const [failed, setFailed] = useState(false);

  if (failed || !src) {
    return <div className="h-10 w-10 shrink-0 rounded-md bg-muted" />;
  }
  return (
    <img
      src={src}
      alt={alt}
      className="h-10 w-10 shrink-0 rounded-md object-cover border border-border"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
  );
}

function OrderCard({ order }: { order: Order }) {
  const date = new Date(order.created_at);
  const dateLabel = Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

  return (
    <div className="rounded-lg border border-border/60 p-3 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium tabular-nums">#{order.id}</p>
        <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
          {STATUS_LABELS[order.status] ?? order.status}
        </span>
      </div>
      {dateLabel ? (
        <p className="text-xs text-muted-foreground">{dateLabel}</p>
      ) : null}
      <div className="space-y-1.5">
        {order.items.map((item) => (
          <div key={item.id} className="flex gap-2 items-center min-w-0">
            <LineImage url={item.image_url} alt={item.subject.slice(0, 40)} />
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium leading-snug line-clamp-2">
                {item.subject}
                {item.variant_label ? ` (${item.variant_label})` : ""}
              </p>
              <p className="text-xs text-muted-foreground tabular-nums">
                {item.quantity} × $
                {item.unit_price != null ? item.unit_price.toFixed(2) : "—"}
              </p>
            </div>
          </div>
        ))}
      </div>
      <p className="text-sm tabular-nums font-medium pt-1 border-t border-border/60">
        ${order.total_amount.toFixed(2)}
      </p>
    </div>
  );
}

/** Floating orders panel — width slide like the session sidebar + cart. */
export function OrdersSheet() {
  const { orders, loading, open, setOpen, refresh } = useOrders();
  /** Keep in DOM while closing so width can animate to 0. */
  const [rendered, setRendered] = useState(false);
  /** Drives width; lags one frame behind mount on open. */
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (open) {
      setRendered(true);
      const id = requestAnimationFrame(() => {
        requestAnimationFrame(() => setExpanded(true));
      });
      return () => cancelAnimationFrame(id);
    }
    setExpanded(false);
    const t = window.setTimeout(() => setRendered(false), ORDERS_MOTION_MS);
    return () => window.clearTimeout(t);
  }, [open]);

  useEffect(() => {
    if (open) {
      void refresh();
    }
  }, [open, refresh]);

  if (!rendered) return null;

  const list = orders ?? [];

  return (
    <div
      className={cn(
        "shrink-0 h-full overflow-hidden transition-[width,margin-inline-start] duration-200 ease-linear",
        expanded ? "ms-2 sm:ms-3" : "ms-0"
      )}
      style={{ width: expanded ? ORDERS_WIDTH_PX : 0 }}
      aria-hidden={!expanded}
    >
      <aside
        className="flex h-full flex-col overflow-hidden rounded-xl border border-border/60 bg-card shadow-modern"
        style={{ width: ORDERS_WIDTH_PX }}
        aria-label="Your orders"
      >
        <div className="shrink-0 flex items-center justify-between gap-2 p-3 border-b border-border/60">
          <div className="min-w-0">
            <p className="text-sm font-medium text-foreground">Your orders</p>
            <p className="text-xs text-muted-foreground truncate">
              {loading
                ? "Loading…"
                : list.length
                ? `${list.length} order(s)`
                : "No orders yet"}
            </p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0"
            onClick={() => setOpen(false)}
            aria-label="Close orders"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          </Button>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-3">
          {loading && list.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">Loading…</p>
          ) : list.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">
              You haven't placed any orders yet.
            </p>
          ) : (
            list.map((order) => <OrderCard key={order.id} order={order} />)
          )}
        </div>
      </aside>
    </div>
  );
}
