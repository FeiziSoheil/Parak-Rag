"use client";

import { forwardRef, useImperativeHandle, useRef, useState } from "react";
import { Textarea } from "@/components/ui/textarea";
import type { ProductSummary } from "@/lib/api";

export type MessageInputHandle = { focus: () => void };

type Props = {
  disabled?: boolean;
  onSend: (message: string, imageFile: File | null, attachedProducts?: ProductSummary[]) => Promise<void>;
  attachedProducts?: ProductSummary[];
  onRemoveProduct?: (productId: number) => void;
};

function IconImage({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <rect width="18" height="18" x="3" y="3" rx="2" ry="2" />
      <circle cx="9" cy="9" r="2" />
      <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" />
    </svg>
  );
}

function IconSend({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d="m22 2-7 20-4-9-9-4Z" />
      <path d="M22 2 11 13" />
    </svg>
  );
}

function IconClose({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d="M18 6 6 18" />
      <path d="m6 6 12 12" />
    </svg>
  );
}

function IconLoader({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      className={`animate-spin ${className ?? ""}`}
      aria-hidden
    >
      <circle cx="12" cy="12" r="10" strokeDasharray="24" strokeDashoffset="8" />
    </svg>
  );
}

const MessageInputInner = forwardRef<MessageInputHandle, Props>(function MessageInput(
  { disabled, onSend, attachedProducts = [], onRemoveProduct },
  ref
) {
  const [text, setText] = useState("");
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [sending, setSending] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useImperativeHandle(ref, () => ({
    focus() {
      textareaRef.current?.focus();
    },
  }));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const toSend = text.trim();
    if ((!toSend && !imageFile && attachedProducts.length === 0) || sending || disabled) return;
    const fileToSend = imageFile;
    const productsToSend = attachedProducts.length > 0 ? attachedProducts : undefined;
    setText("");
    setImageFile(null);
    setSending(true);
    try {
      await onSend(toSend || "(Image)", fileToSend, productsToSend);
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  }

  return (
    <div className="sticky bottom-0 left-0 right-0 p-3 sm:p-4 flex justify-center bg-background shadow-[0_-4px_12px_-2px_rgba(0,0,0,0.08)] dark:shadow-[0_-4px_12px_-2px_rgba(0,0,0,0.25)]">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-[min(100%,28rem)] focus-within:max-w-[min(100%,42rem)] bg-background/95 dark:bg-background/90 backdrop-blur-sm shadow-lg shadow-black/5 p-3 sm:p-4 transition-[max-width] duration-300 ease-out focus-within:shadow-xl focus-within:shadow-black/10"
      >
        {(attachedProducts.length > 0 || imageFile) && (
          <div className="mb-3 flex flex-wrap items-center gap-2 animate-slide-down">
            {attachedProducts.map((p) => (
              <div
                key={p.product_id}
                className="flex items-center gap-2 rounded-lg border border-border bg-muted/50 px-2.5 py-1.5 text-sm"
              >
                <span className="max-w-[140px] truncate text-foreground" title={p.subject}>
                  {p.subject}
                </span>
                {onRemoveProduct && (
                  <button
                    type="button"
                    onClick={() => onRemoveProduct(p.product_id)}
                    className="p-0.5 rounded text-muted-foreground hover:text-destructive transition-colors"
                    title="Remove from attachment"
                    aria-label="Remove from attachment"
                  >
                    <IconClose />
                  </button>
                )}
              </div>
            ))}
            {imageFile && (
              <>
                <div className="relative">
                  <img
                    src={URL.createObjectURL(imageFile)}
                    alt="Preview"
                    className="h-12 w-12 object-cover rounded-lg border border-border"
                  />
                  <button
                    type="button"
                    onClick={() => setImageFile(null)}
                    className="absolute -top-1 -right-1 p-1 rounded bg-card border border-border text-muted-foreground hover:text-destructive transition-colors"
                    title="Remove image"
                    aria-label="Remove image"
                  >
                    <IconClose />
                  </button>
                </div>
                <span className="text-xs text-muted-foreground">{imageFile.name}</span>
              </>
            )}
          </div>
        )}
        <div className="flex items-center py-2 px-2 gap-1 rounded-3xl border border-border bg-background focus-within:border-foreground/15 focus-within:ring-1 focus-within:ring-ring/15 transition-all overflow-hidden">
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => setImageFile(e.target.files?.[0] ?? null)}
        />
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled || sending}
          className="flex items-center justify-center w-9 h-9 shrink-0 text-muted-foreground hover:text-foreground rounded-lg transition-colors disabled:opacity-50 disabled:pointer-events-none ml-1"
          title="Attach image"
          aria-label="Attach image"
        >
          <IconImage />
        </button>
        <Textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Message…"
          rows={1}
          className="min-h-[20px] max-h-28 resize-none flex-1 rounded-none border-0 bg-transparent shadow-none focus-visible:ring-0 focus-visible:ring-offset-0 py-2.5 px-2 text-sm placeholder:text-muted-foreground"
          disabled={disabled || sending}
        />
        <button
          type="submit"
          disabled={(!text.trim() && !imageFile && attachedProducts.length === 0) || sending || disabled}
          className="flex items-center justify-center w-9 h-9 shrink-0 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:pointer-events-none mr-1"
          title="Send"
          aria-label="Send message"
        >
          {sending ? (
            <IconLoader className="text-primary-foreground" />
          ) : (
            <IconSend />
          )}
        </button>
      </div>
    </form>
    </div>
  );
});

export { MessageInputInner as MessageInput };
