"use client";

import { useState, useEffect } from "react";
import type { ProductSummary, ProductVariant } from "@/lib/api";
import { getProductImageUrl } from "@/lib/api";
import { Button } from "@/components/ui/button";

function formatVariantLabel(v: ProductVariant): string {
  if (v.attributes && v.attributes.length > 0) {
    return v.attributes
      .map((a) => {
        const n = (a.name || "").trim();
        const val = (a.value || "").trim();
        return n && val ? `${n}: ${val}` : val || n || "";
      })
      .filter(Boolean)
      .join(", ") || "—";
  }
  return v.name || v.color || "—";
}

type Props = {
  product: ProductSummary;
  onClose: () => void;
};

function SidebarProductImage({ url, alt }: { url: string; alt: string }) {
  const [src, setSrc] = useState<string>(() => url);
  const [failed, setFailed] = useState(false);
  const proxyUrl = getProductImageUrl(url);

  const handleError = () => {
    if (src === url && proxyUrl && proxyUrl !== url) {
      setSrc(proxyUrl);
    } else {
      setFailed(true);
    }
  };

  if (failed || !url?.trim()) {
    return (
      <div className="w-full aspect-square max-h-64 bg-muted flex items-center justify-center text-muted-foreground rounded-lg">
        <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect width="18" height="18" x="3" y="3" rx="2" ry="2" />
          <circle cx="9" cy="9" r="2" />
          <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" />
        </svg>
      </div>
    );
  }
  return (
    <img
      src={src}
      alt={alt}
      className="w-full aspect-square max-h-64 object-cover rounded-lg"
      referrerPolicy="no-referrer"
      onError={handleError}
    />
  );
}

function VariantThumbnail({ url, alt }: { url: string; alt: string }) {
  const [src, setSrc] = useState<string>(() => url);
  const [failed, setFailed] = useState(false);
  const proxyUrl = getProductImageUrl(url);

  const handleError = () => {
    if (src === url && proxyUrl && proxyUrl !== url) setSrc(proxyUrl);
    else setFailed(true);
  };

  if (failed || !url?.trim()) {
    return (
      <div className="w-12 h-12 shrink-0 rounded-md bg-muted flex items-center justify-center text-muted-foreground">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect width="18" height="18" x="3" y="3" rx="2" ry="2" />
          <circle cx="9" cy="9" r="2" />
          <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" />
        </svg>
      </div>
    );
  }
  return (
    <img
      src={src}
      alt={alt}
      className="w-12 h-12 shrink-0 rounded-md object-cover border border-border"
      referrerPolicy="no-referrer"
      onError={handleError}
    />
  );
}

export function ProductSidebar({ product, onClose }: Props) {
  const imgSrc = product.image_url?.trim() || null;
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  return (
    <aside
      className="w-full min-w-0 border-l border-border bg-card/50 flex flex-col h-full overflow-hidden transition-opacity duration-300 ease-in-out"
      style={{ opacity: mounted ? 1 : 0 }}
    >
      <div className="shrink-0 flex items-center justify-between gap-2 p-3 border-b border-border">
        <span className="text-sm font-medium text-foreground">Product details</span>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0"
          onClick={onClose}
          aria-label="Close sidebar"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 6 6 18" />
            <path d="m6 6 12 12" />
          </svg>
        </Button>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-4">
        {imgSrc ? (
          <SidebarProductImage url={imgSrc} alt={product.subject.slice(0, 80)} />
        ) : (
          <div className="w-full aspect-square max-h-64 bg-muted rounded-lg flex items-center justify-center text-muted-foreground">
            <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect width="18" height="18" x="3" y="3" rx="2" ry="2" />
              <circle cx="9" cy="9" r="2" />
              <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" />
            </svg>
          </div>
        )}
        <div>
          <h3 className="text-sm font-semibold text-foreground leading-snug">
            {product.subject}
          </h3>
          {product.price != null && (
            <p className="mt-1 text-base font-medium text-foreground">
              ${typeof product.price === "number" ? product.price.toFixed(2) : product.price}
            </p>
          )}
          {product.category_name && (
            <p className="mt-1 text-xs text-muted-foreground">
              {product.category_name}
            </p>
          )}
        </div>
        {product.variants && product.variants.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1.5">
              Variants
            </h4>
            <ul className="space-y-0 text-sm">
              {product.variants.map((v, i) => (
                <li key={i} className="flex items-center gap-3 py-2 border-b border-border last:border-b-0 last:pb-0">
                  {v.image?.trim() ? (
                    <VariantThumbnail
                      url={v.image.trim()}
                      alt={v.attributes?.map((a) => a.value).filter(Boolean).join(" ") || product.subject.slice(0, 40)}
                    />
                  ) : (
                    <div className="w-12 h-12 shrink-0 rounded-md bg-muted flex items-center justify-center text-muted-foreground">
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <rect width="18" height="18" x="3" y="3" rx="2" ry="2" />
                        <circle cx="9" cy="9" r="2" />
                        <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" />
                      </svg>
                    </div>
                  )}
                  <span className="min-w-0 flex-1">
                    {v.attributes && v.attributes.length > 0 ? (
                      v.attributes.map((a, j) => {
                        const n = (a.name || "").trim();
                        const val = (a.value || "").trim();
                        if (!n && !val) return null;
                        return (
                          <span key={j}>
                            {j > 0 && (
                              <span className="text-muted-foreground/60 mx-1"> · </span>
                            )}
                            {n && (
                              <span className="text-muted-foreground font-normal">
                                {n}
                                {val ? ": " : ""}
                              </span>
                            )}
                            {val && (
                              <span className="text-foreground font-medium">
                                {val}
                              </span>
                            )}
                          </span>
                        );
                      })
                    ) : (
                      <span className="text-foreground">{v.name || v.color || "—"}</span>
                    )}
                  </span>
                  {v.price != null && (
                    <span className="text-muted-foreground shrink-0 tabular-nums">
                      ${typeof v.price === "number" ? v.price.toFixed(2) : v.price}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </aside>
  );
}
