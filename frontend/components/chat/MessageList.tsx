"use client";

import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";
import { Volume2, User } from "lucide-react";
import type { ProductSummary } from "@/lib/api";
import { getProductImageUrl } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { StreamingTypewriter } from "@/components/ui/typewriter-effect";
import ShinyText from "@/components/ui/ShinyText";
import { AIAvatar } from "./AIAvatar";

const LOADING_PHRASES = [
  "Finding products...",
  "Gathering information...",
  "Searching the catalog...",
  "Please wait a moment...",
  "Preparing suggestions...",
];
const LOADING_PHRASE_INTERVAL_MS = 3200;

export type MessageEntry = {
  id: number;
  role: string;
  content: string;
  image_url: string | null;
  products?: ProductSummary[];
  /** Products attached by the user to this message (user messages only) */
  attachedProducts?: ProductSummary[];
  /** Base64-encoded MP3 from voice-chat response (assistant messages only) */
  audioBase64?: string;
  /** When true, user message is waiting for STT — show loader in bubble (user messages only) */
  transcribing?: boolean;
  created_at?: string;
};

export type SuggestedPromptItem = { text: string; icon: React.ComponentType<{ className?: string }> };

type Props = {
  messages: MessageEntry[];
  sending?: boolean;
  /** When true, show ShinyText loader (Qdrant search). When false, show dots loader. */
  expectsQdrantSearch?: boolean;
  welcomeMessage?: string | null;
  /** Shown below welcome when chat is empty; clicking sends that text. */
  suggestedPrompts?: SuggestedPromptItem[];
  onSuggestedPromptClick?: (text: string) => void;
  onRegenerate?: () => void;
  selectedProductIds?: Set<number>;
  onProductSelect?: (product: ProductSummary) => void;
  /** Ref for the last assistant voice audio element (for playback control / interruption). */
  voiceAudioRef?: React.RefObject<HTMLAudioElement | null>;
  onAudioPlayStart?: () => void;
  onAudioPlayEnd?: () => void;
  /** Read aloud: backend detects language and returns TTS; caller handles playback. */
  onReadAloud?: (text: string) => Promise<void>;
  /** Avatar state and emotion for display next to assistant messages */
  avatarState?: "idle" | "thinking" | "speaking";
  avatarEmotion?: "neutral" | "happy" | "excited" | "sad" | "confused" | "surprised" | "love" | "annoyed" | "angry" | "sleepy";
  /** Called when user clicks avatar */
  onAvatarClick?: () => void;
  /** Optional user avatar URL to show next to user messages */
  userAvatarUrl?: string | null;
};

function ProductCardImage({ url, alt }: { url: string; alt: string }) {
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
      <div className="w-full h-32 bg-muted flex items-center justify-center text-muted-foreground text-xs">
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
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
      className="w-full h-32 object-cover"
      referrerPolicy="no-referrer"
      onError={handleError}
    />
  );
}

function ProductCards({
  products,
  selectedProductIds,
  onProductSelect,
}: {
  products: ProductSummary[];
  selectedProductIds?: Set<number>;
  onProductSelect?: (product: ProductSummary) => void;
}) {
  const isSelectable = typeof onProductSelect === "function";
  return (
    <div className="mt-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {products.map((p) => {
        const imgSrc = p.image_url?.trim() || null;
        const selected = selectedProductIds?.has(p.product_id) ?? false;
        const Wrapper = isSelectable ? "button" : "div";
        return (
          <Wrapper
            key={p.product_id}
            type={isSelectable ? "button" : undefined}
            onClick={isSelectable ? () => onProductSelect?.(p) : undefined}
            className={`w-full text-left rounded-xl border overflow-hidden transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 relative ${
              isSelectable
                ? "cursor-pointer hover:bg-muted/50 " + (selected ? "border-primary ring-2 ring-primary/30 bg-primary/5" : "border-border bg-card")
                : "border-border bg-card hover:bg-muted/50"
            }`}
          >
            {selected && isSelectable && (
              <div className="absolute top-2 right-2 z-10 w-6 h-6 rounded-full bg-primary text-primary-foreground flex items-center justify-center shadow">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </div>
            )}
            <div className="relative">
              {imgSrc ? (
                <ProductCardImage url={imgSrc} alt={p.subject.slice(0, 60)} />
              ) : (
                <div className="w-full h-32 bg-muted flex items-center justify-center text-muted-foreground text-xs">
                  <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <rect width="18" height="18" x="3" y="3" rx="2" ry="2" />
                    <circle cx="9" cy="9" r="2" />
                    <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" />
                  </svg>
                </div>
              )}
            </div>
            <div className="p-3">
              <p className="text-sm font-medium text-foreground">
                {p.subject}
              </p>
              <div className="flex items-center justify-between mt-1.5">
                {p.price != null && (
                  <p className="text-sm text-muted-foreground">
                    ${typeof p.price === "number" ? p.price.toFixed(2) : p.price}
                  </p>
                )}
                {p.category_name && (
                  <span className="text-xs text-muted-foreground">{p.category_name}</span>
                )}
              </div>
            </div>
          </Wrapper>
        );
      })}
      </div>
    </div>
  );
}

/** Normalize ** bold ** with inner spaces to **bold** so markdown renders correctly. */
function normalizeBoldMarkdown(text: string): string {
  return text.replace(/\*\*\s*([^*]+?)\s*\*\*/g, (_, inner) => "**" + inner.trim() + "**");
}

const MARKDOWN_CONTENT_CLASS =
  "markdown-message message-content text-sm leading-relaxed [&_ul]:list-disc [&_ul]:ml-4 [&_ol]:list-decimal [&_ol]:ml-4 [&_li]:my-0.5 [&_p]:my-1.5 first:[&_p]:mt-0 last:[&_p]:mb-0 [&_strong]:font-semibold [&_strong]:text-foreground";

/** Renders assistant message content as Markdown so **bold**, lists, and line breaks display correctly. */
function MarkdownContent({ content }: { content: string }) {
  if (!content?.trim()) return null;
  const normalized = normalizeBoldMarkdown(content);
  return (
    <div dir="auto" className={MARKDOWN_CONTENT_CLASS}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {normalized}
      </ReactMarkdown>
    </div>
  );
}

/** Renders assistant message with typewriter effect; after completion shows Markdown. */
function AssistantMessageContent({
  content,
  messageId,
  typewriterCompleteIds,
  onTypewriterComplete,
}: {
  content: string;
  messageId: number;
  typewriterCompleteIds: Set<number>;
  onTypewriterComplete: (id: number) => void;
}) {
  if (!content?.trim()) return null;
  const showMarkdown = typewriterCompleteIds.has(messageId);
  if (showMarkdown) {
    return <MarkdownContent content={content} />;
  }
  return (
    <div dir="auto" className={MARKDOWN_CONTENT_CLASS}>
      <StreamingTypewriter
        text={content}
        speed={18}
        showCursor={true}
        className="text-sm leading-relaxed"
        cursorClassName="inline-block w-0.5 h-4 bg-foreground/70 ml-0.5 align-middle"
        onComplete={() => onTypewriterComplete(messageId)}
      />
    </div>
  );
}


/** Small avatar shown next to user messages: image if URL provided, else User icon. */
function UserAvatar({ avatarUrl, size = 44 }: { avatarUrl?: string | null; size?: number }) {
  const resolvedUrl = avatarUrl?.trim() ? avatarUrl : null;
  return (
    <div
      className="shrink-0 rounded-full bg-primary/20 border border-border flex items-center justify-center overflow-hidden shadow-modern"
      style={{ width: size, height: size }}
      aria-label="You"
    >
      {resolvedUrl ? (
        <img src={resolvedUrl} alt="" className="w-full h-full object-cover" referrerPolicy="no-referrer" />
      ) : (
        <User className="text-primary" style={{ width: size * 0.5, height: size * 0.5 }} strokeWidth={2} />
      )}
    </div>
  );
}

function CopyIcon({ className }: { className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
      <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
    </svg>
  );
}

function RegenerateIcon({ className }: { className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M21 2v6h-6" />
      <path d="M3 12a9 9 0 0 1 15-6.7L21 8" />
      <path d="M3 22v-6h6" />
      <path d="M21 12a9 9 0 0 1-15 6.7L3 16" />
    </svg>
  );
}

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}

export function MessageList({ messages, sending, expectsQdrantSearch = false, welcomeMessage, suggestedPrompts, onSuggestedPromptClick, onRegenerate, selectedProductIds, onProductSelect, voiceAudioRef, onAudioPlayStart, onAudioPlayEnd, onReadAloud, avatarState = "idle", avatarEmotion = "neutral", onAvatarClick, userAvatarUrl }: Props) {
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const [readAloudLoadingId, setReadAloudLoadingId] = useState<number | null>(null);
  const [typewriterCompleteIds, setTypewriterCompleteIds] = useState<Set<number>>(() => new Set());
  const [loadingPhraseIndex, setLoadingPhraseIndex] = useState(0);
  const hadMessagesRef = useRef(false);
  const lastVoiceAudioRef = useRef<HTMLAudioElement | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll to bottom when new messages arrive or sending state changes
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages.length, sending]);

  useEffect(() => {
    if (!sending) {
      setLoadingPhraseIndex(0);
      return;
    }
    const id = setInterval(() => {
      setLoadingPhraseIndex((i) => (i + 1) % LOADING_PHRASES.length);
    }, LOADING_PHRASE_INTERVAL_MS);
    return () => clearInterval(id);
  }, [sending]);

  const setVoiceAudioRef = (el: HTMLAudioElement | null) => {
    lastVoiceAudioRef.current = el;
    if (voiceAudioRef) (voiceAudioRef as React.MutableRefObject<HTMLAudioElement | null>).current = el;
  };

  // When switching session, clear typewriter state
  useEffect(() => {
    if (messages.length === 0) {
      hadMessagesRef.current = false;
      setTypewriterCompleteIds(new Set());
      return;
    }
    // Only treat as "loaded from server" when we go from 0 to having messages (initial load)
    if (!hadMessagesRef.current) {
      hadMessagesRef.current = true;
      const assistantIds = new Set(messages.filter((m) => m.role === "assistant").map((m) => m.id));
      if (assistantIds.size > 0) setTypewriterCompleteIds(assistantIds);
    }
  }, [messages.length, messages]);

  async function handleCopy(content: string, messageId: number) {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedId(messageId);
      setTimeout(() => setCopiedId(null), 2000);
      toast.success("Copied to clipboard");
    } catch {
      toast.error("Could not copy");
    }
  }

  async function handleReadAloud(content: string, messageId: number) {
    if (!onReadAloud || !content?.trim()) return;
    setReadAloudLoadingId(messageId);
    try {
      await onReadAloud(content);
    } finally {
      setReadAloudLoadingId(null);
    }
  }

  const lastMessageIndex = messages.length - 1;
  const isLastAssistant = (idx: number) => {
    const m = messages[idx];
    return m?.role === "assistant" && idx === lastMessageIndex && !sending;
  };
  
  // Find the last assistant message index for avatar display
  const lastAssistantIndex = messages.findLastIndex(m => m.role === "assistant");

  return (
    <TooltipProvider delayDuration={300}>
      <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden py-8 space-y-6 no-scrollbar">
        {messages.length === 0 && !sending && !welcomeMessage && (
          <div className="text-center py-16">
            <p className="text-muted-foreground text-sm">
              No messages yet. Ask a question or upload an image.
            </p>
          </div>
        )}
        {messages.length === 0 && welcomeMessage && !sending && (
          <div className="min-h-full flex flex-col justify-center py-8">
            <div className="space-y-5 animate-fade-in flex flex-col items-center text-center">
              <div 
                className="cursor-pointer transition-transform hover:scale-105 active:scale-95"
                onClick={onAvatarClick}
                role="button"
                aria-label="AI Avatar"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onAvatarClick?.();
                  }
                }}
              >
                <AIAvatar state={avatarState} emotion={avatarEmotion} size={100} className="mb-2" />
              </div>
              <h2 dir="auto" className="text-lg font-semibold text-foreground leading-snug">
                {welcomeMessage}
              </h2>
              {suggestedPrompts && suggestedPrompts.length > 0 && onSuggestedPromptClick && (
                <div className="flex flex-wrap gap-2">
                  {suggestedPrompts.map((item) => {
                    const Icon = item.icon;
                    return (
                      <button
                        key={item.text}
                        type="button"
                        onClick={() => onSuggestedPromptClick(item.text)}
                        className="inline-flex items-center gap-2 rounded-full border border-border bg-muted/80 px-4 py-2 text-sm text-foreground hover:bg-muted hover:border-primary/50 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                      >
                        <Icon className="h-4 w-4 shrink-0" />
                        <span>{item.text}</span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}
        {messages.map((m, idx) => {
          // Show avatar only for last assistant message AND only when not currently sending
          const isLastAssistantMsg = m.role === "assistant" && idx === lastAssistantIndex && !sending;
          const isUserMsg = m.role === "user";
          return (
          <div
            key={m.id}
            className={`flex animate-fade-in ${isUserMsg ? "flex-row items-end justify-end gap-3" : isLastAssistantMsg ? "flex-row items-start gap-3" : "flex-col items-start"}`}
          >
            {/* Avatar for last assistant message (only when not sending) */}
            {isLastAssistantMsg && (
              <div 
                className="shrink-0 mt-1 cursor-pointer transition-transform hover:scale-105 active:scale-95"
                onClick={onAvatarClick}
                role="button"
                aria-label="AI Avatar"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onAvatarClick?.();
                  }
                }}
              >
                <AIAvatar state={avatarState} emotion={avatarEmotion} size={56} className="shadow-modern" />
              </div>
            )}
            <div className={`flex flex-col flex-1 ${isUserMsg ? "items-end" : "items-start"}`}>
            <div
              className={`max-w-[85%] w-fit rounded-xl px-4 py-[5px] ${
                m.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-foreground border border-border/50"
              }`}
            >
              {m.role === "user" && m.image_url && (
                <div className="mb-3 rounded-xl overflow-hidden border border-primary-foreground/10">
                  <img
                    src={m.image_url}
                    alt="User upload"
                    className="max-h-48 w-full object-cover"
                  />
                </div>
              )}
              {m.role === "user" && m.attachedProducts && m.attachedProducts.length > 0 && (
                <div className="mb-3 flex flex-wrap gap-1.5">
                  {m.attachedProducts.map((p) => (
                    <span
                      key={p.product_id}
                      className="inline-flex items-center gap-1.5 rounded-md bg-primary-foreground/15 px-2 py-1 text-xs"
                    >
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span className="max-w-[160px] truncate cursor-default">
                            {p.subject}
                          </span>
                        </TooltipTrigger>
                        <TooltipContent side="top">
                          <p>{p.subject}</p>
                        </TooltipContent>
                      </Tooltip>
                      {p.price != null && (
                        <span className="shrink-0 opacity-90">
                          ${typeof p.price === "number" ? p.price.toFixed(2) : p.price}
                        </span>
                      )}
                    </span>
                  ))}
                </div>
              )}
              {m.role === "assistant" ? (
                <>
                  <AssistantMessageContent
                    content={m.content}
                    messageId={m.id}
                    typewriterCompleteIds={typewriterCompleteIds}
                    onTypewriterComplete={(id) => setTypewriterCompleteIds((prev) => new Set(prev).add(id))}
                  />
                  {m.audioBase64 && idx === messages.length - 1 && !sending && (
                    <audio
                      ref={setVoiceAudioRef}
                      src={`data:audio/mpeg;base64,${m.audioBase64}`}
                      autoPlay
                      className="hidden"
                      aria-hidden
                      onLoadedData={() => lastVoiceAudioRef.current?.play().catch(() => {})}
                      onPlay={onAudioPlayStart}
                      onEnded={onAudioPlayEnd}
                    />
                  )}
                </>
              ) : (
                <>
                  {m.transcribing ? (
                    <div className="py-1">
                      <ShinyText
                        text="Converting speech to text…"
                        speed={1.2}
                        spread={100}
                        direction="left"
                        yoyo
                        pauseOnHover
                        color="#717171"
                        shineColor="#707070"
                        className="text-sm"
                      />
                    </div>
                  ) : m.content ? (
                    <p dir="auto" className="message-content text-sm leading-relaxed whitespace-pre-line">
                      {m.content
                        .split(/\n\n+/)
                        .map((para) => para.replace(/\n/g, " ").trim())
                        .filter(Boolean)
                        .join("\n")}
                    </p>
                  ) : m.attachedProducts?.length ? (
                    <p className="text-sm text-primary-foreground/80 italic">Question about attached product(s)</p>
                  ) : null}
                </>
              )}
              {m.role === "assistant" && m.products && m.products.length > 0 && (
                <ProductCards
                  products={m.products}
                  selectedProductIds={selectedProductIds}
                  onProductSelect={onProductSelect}
                />
              )}
            </div>
            {m.role === "assistant" && m.content && (
              <div className="mt-1.5 flex items-center gap-0.5">
                {onReadAloud && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-8 w-8 text-muted-foreground hover:text-foreground"
                        onClick={() => handleReadAloud(m.content, m.id)}
                        disabled={readAloudLoadingId === m.id}
                        aria-label="Read aloud"
                      >
                        {readAloudLoadingId === m.id ? (
                          <span className="h-4 w-4 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent" />
                        ) : (
                          <Volume2 className="h-4 w-4 shrink-0" />
                        )}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top">
                      <p>{readAloudLoadingId === m.id ? "Preparing…" : "Read aloud"}</p>
                    </TooltipContent>
                  </Tooltip>
                )}
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-8 w-8 text-muted-foreground hover:text-foreground"
                      onClick={() => handleCopy(m.content, m.id)}
                      aria-label={copiedId === m.id ? "Copied" : "Copy"}
                    >
                      {copiedId === m.id ? (
                        <CheckIcon className="h-4 w-4 shrink-0" />
                      ) : (
                        <CopyIcon className="h-4 w-4 shrink-0" />
                      )}
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="top">
                    <p>{copiedId === m.id ? "Copied" : "Copy"}</p>
                  </TooltipContent>
                </Tooltip>
                {onRegenerate && isLastAssistant(idx) && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-8 w-8 text-muted-foreground hover:text-foreground"
                        onClick={onRegenerate}
                        aria-label="Regenerate"
                      >
                        <RegenerateIcon className="h-4 w-4 shrink-0" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top">
                      <p>Regenerate</p>
                    </TooltipContent>
                  </Tooltip>
                )}
              </div>
            )}
            </div>
            {/* User avatar next to user messages */}
            {isUserMsg && (
              <UserAvatar avatarUrl={userAvatarUrl} size={44} />
            )}
          </div>
        );
        })}
        {sending && (
          <div className="flex flex-row items-start gap-3 animate-fade-in">
            {/* Avatar while thinking */}
            <div 
              className="shrink-0 mt-1 cursor-pointer transition-transform hover:scale-105 active:scale-95"
              onClick={onAvatarClick}
              role="button"
              aria-label="AI Avatar"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onAvatarClick?.();
                }
              }}
            >
              <AIAvatar state="thinking" emotion={avatarEmotion} size={56} className="shadow-modern" />
            </div>
            <div className="flex flex-col items-start flex-1">
              <div className="max-w-[85%] rounded-xl px-4 py-1 bg-muted text-foreground border border-border/50">
                <ShinyText
                  text={expectsQdrantSearch ? LOADING_PHRASES[loadingPhraseIndex] : "Thinking…"}
                  speed={1.2}
                  delay={0}
                  spread={100}
                  direction="left"
                  yoyo
                  pauseOnHover
                  color="var(--muted-foreground)"
                  shineColor="var(--foreground)"
                  className="text-sm"
                />
              </div>
            </div>
          </div>
        )}
        {/* Scroll anchor for auto-scroll to bottom */}
        <div ref={messagesEndRef} />
      </div>
    </TooltipProvider>
  );
}
