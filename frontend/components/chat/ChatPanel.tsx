"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { TrendingUp, Search, ShoppingCart, CreditCard } from "lucide-react";
import { MessageList, type MessageEntry, type SuggestedPromptItem } from "./MessageList";
import { MessageInput, type MessageInputHandle } from "./MessageInput";
import { ProductSidebar } from "./ProductSidebar";
import type { AIAvatarState, AIAvatarEmotion } from "./AIAvatar";
import { Skeleton } from "@/components/ui/skeleton";
import { getCurrentUser, getSessionMessages, sendChat, sendVoiceChat, readAloud, detectIntent, voiceDetectIntent, getAvatarUrl, type ProductSummary, type ProductVariant, type UserProfile } from "@/lib/api";
import { buildSidebarProduct, commerceFollowUp } from "@/lib/commerceChat.mjs";
import { useCart } from "@/contexts/CartContext";
import { cn } from "@/lib/utils";

/** Match cart + main floating sidebar motion */
const PRODUCT_PANEL_MOTION_MS = 200;

function getDisplayName(user: UserProfile | null): string {
  if (!user) return "";
  const full = [user.first_name, user.last_name].filter(Boolean).join(" ").trim();
  return full || user.username || "";
}

const WELCOME_DASHBOARD_BASE = "Select a chat or create a new one to begin.";
const WELCOME_NEW_CHAT_BASE = "I'm here to help. Ask about products, search the catalog, or get answers from our FAQ.";

const SUGGESTED_PROMPTS: SuggestedPromptItem[] = [
  { text: "Show me popular products", icon: TrendingUp },
  { text: "Search for products under $20", icon: Search },
  { text: "How do I place an order?", icon: ShoppingCart },
  { text: "What are the payment methods?", icon: CreditCard },
];

const SIDEBAR_WIDTH_MIN = 280;
const SIDEBAR_WIDTH_MAX = 600;
const SIDEBAR_WIDTH_DEFAULT = 320; // same default width as cart panel

type Props = {
  sessionId: number | null;
};

export function ChatPanel({ sessionId }: Props) {
  const { addItem, refresh } = useCart();
  const [messages, setMessages] = useState<MessageEntry[]>([]);
  const [selectedProducts, setSelectedProducts] = useState<ProductSummary[]>([]);
  /** Product currently shown in the right sidebar (last selected for view). */
  const [sidebarProduct, setSidebarProduct] = useState<ProductSummary | null>(null);
  const [sidebarVariant, setSidebarVariant] = useState<ProductVariant | null>(null);
  const handleSidebarVariant = useCallback((variant: ProductVariant | null) => {
    setSidebarVariant(variant);
  }, []);
  /** During close we keep rendering the sidebar until width transition finishes. */
  const [closingProduct, setClosingProduct] = useState<ProductSummary | null>(null);
  /** Drives width transition; stays true while closing so width animates to 0 before unmount. */
  const [sidebarWidthOpen, setSidebarWidthOpen] = useState(false);
  /** Sidebar width in px (when open). Clamped between SIDEBAR_WIDTH_MIN and SIDEBAR_WIDTH_MAX. */
  const [sidebarWidthPx, setSidebarWidthPx] = useState(SIDEBAR_WIDTH_DEFAULT);
  const [isResizing, setIsResizing] = useState(false);
  const resizeStartRef = useRef({ x: 0, width: 0 });
  const productExpandRafRef = useRef<number | null>(null);
  const productCloseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  /** True when current request triggers Qdrant search (product/FAQ/store). Show ShinyText only then. */
  const [expectsQdrantSearch, setExpectsQdrantSearch] = useState(false);
  const [user, setUser] = useState<UserProfile | null>(null);
  const messageInputRef = useRef<MessageInputHandle>(null);
  /** Unique negative ids for new messages in this session (so typewriter runs for each new assistant message). */
  const nextTempIdRef = useRef(-1);
  /** When AI voice response is playing; VAD must be paused to avoid feedback loop. */
  const [isAISpeaking, setAISpeaking] = useState(false);
  const voiceAudioRef = useRef<HTMLAudioElement | null>(null);
  const readAloudAudioRef = useRef<HTMLAudioElement | null>(null);
  const audioEndDelayRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  
  // Avatar emotion — context-based (not cycling randomly)
  const [avatarEmotion, setAvatarEmotion] = useState<AIAvatarEmotion>("neutral");
  const emotionTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  
  // Track clicks for "angry" emotion (if user clicks avatar too much)
  const avatarClickTimestamps = useRef<number[]>([]);
  const ANGRY_CLICK_THRESHOLD = 5; // clicks
  const ANGRY_CLICK_WINDOW_MS = 3000; // 3 seconds
  const ANGRY_DURATION_MS = 5000; // stay angry for 5 seconds
  
  // LLM-suggested emotion: show for 5s after each chat/voice response, then reset to neutral
  const LLM_EMOTION_DURATION_MS = 5000;
  const ALLOWED_LLM_EMOTIONS: AIAvatarEmotion[] = ["neutral", "happy", "excited", "sad", "confused", "surprised", "love"];
  
  // If response takes > 8s, show "annoyed" emotion
  const ANNOYED_THRESHOLD_MS = 8000;
  const [sendingElapsedMs, setSendingElapsedMs] = useState(0);
  const sendingStartRef = useRef<number | null>(null);
  const sendingTickRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // When user doesn't send for a long time, show "sleepy" (sleeping) avatar
  const SLEEPY_IDLE_MS = 120000; // 2 minutes
  const [idleLong, setIdleLong] = useState(false);
  const lastMessageSentAtRef = useRef<number>(0);
  const sleepyCheckRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const handleAudioPlayStart = useCallback(() => {
    if (audioEndDelayRef.current) {
      clearTimeout(audioEndDelayRef.current);
      audioEndDelayRef.current = null;
    }
    setAISpeaking(true);
  }, []);

  const handleAudioPlayEnd = useCallback(() => {
    if (audioEndDelayRef.current) clearTimeout(audioEndDelayRef.current);
    audioEndDelayRef.current = setTimeout(() => {
      setAISpeaking(false);
      audioEndDelayRef.current = null;
    }, 500);
  }, []);

  const stopAIPlayback = useCallback(() => {
    if (audioEndDelayRef.current) {
      clearTimeout(audioEndDelayRef.current);
      audioEndDelayRef.current = null;
    }
    setAISpeaking(false);
    voiceAudioRef.current?.pause();
    readAloudAudioRef.current?.pause();
  }, []);

  useEffect(() => {
    return () => {
      if (audioEndDelayRef.current) clearTimeout(audioEndDelayRef.current);
    };
  }, []);

  // Track sending duration — if > 8s, avatar shows "annoyed"
  useEffect(() => {
    if (sending) {
      sendingStartRef.current = Date.now();
      setSendingElapsedMs(0);
      sendingTickRef.current = setInterval(() => {
        const start = sendingStartRef.current;
        if (start != null) setSendingElapsedMs(Date.now() - start);
      }, 500);
      return () => {
        if (sendingTickRef.current) clearInterval(sendingTickRef.current);
        sendingTickRef.current = null;
      };
    }
    sendingStartRef.current = null;
    sendingTickRef.current = null;
    setSendingElapsedMs(0);
  }, [sending]);

  // Normalize LLM suggested_emotion (backend may return "worried" -> map to "confused"; only allow known emotions)
  const applySuggestedEmotion = useCallback((suggested_emotion: string | undefined) => {
    if (!suggested_emotion || suggested_emotion === "neutral") return;
    const normalized = suggested_emotion.toLowerCase().trim() === "worried" ? "confused" : suggested_emotion.toLowerCase().trim();
    if (!ALLOWED_LLM_EMOTIONS.includes(normalized as AIAvatarEmotion)) return;
    if (emotionTimeoutRef.current) clearTimeout(emotionTimeoutRef.current);
    setAvatarEmotion(normalized as AIAvatarEmotion);
    emotionTimeoutRef.current = setTimeout(() => {
      setAvatarEmotion("neutral");
      emotionTimeoutRef.current = null;
    }, LLM_EMOTION_DURATION_MS);
  }, []);

  // Handle avatar click — if clicked too much, get angry
  const handleAvatarClick = useCallback(() => {
    const now = Date.now();
    // Add current click
    avatarClickTimestamps.current.push(now);
    // Remove clicks older than window
    avatarClickTimestamps.current = avatarClickTimestamps.current.filter(
      (ts) => now - ts < ANGRY_CLICK_WINDOW_MS
    );
    
    // If too many clicks, get angry
    if (avatarClickTimestamps.current.length >= ANGRY_CLICK_THRESHOLD) {
      if (emotionTimeoutRef.current) clearTimeout(emotionTimeoutRef.current);
      setAvatarEmotion("angry");
      avatarClickTimestamps.current = []; // Reset
      
      // Return to neutral after duration
      emotionTimeoutRef.current = setTimeout(() => {
        setAvatarEmotion("neutral");
        emotionTimeoutRef.current = null;
      }, ANGRY_DURATION_MS);
    }
  }, []);

  // Cleanup emotion timeout on unmount
  useEffect(() => {
    return () => {
      if (emotionTimeoutRef.current) clearTimeout(emotionTimeoutRef.current);
    };
  }, []);

  useEffect(() => {
    getCurrentUser().then(setUser);
  }, []);

  // Keyboard shortcuts: / → open compose dialog; Escape → stop AI voice
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const inInput =
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        (e.target as HTMLElement)?.getAttribute?.("contenteditable") === "true";
      if (e.key === "/" && !inInput) {
        e.preventDefault();
        messageInputRef.current?.openCompose();
        return;
      }
      if (e.key === "Escape" && isAISpeaking) {
        e.preventDefault();
        stopAIPlayback();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isAISpeaking, stopAIPlayback]);

  useEffect(() => {
    if (!sessionId) {
      setMessages([]);
      setIdleLong(false);
      return;
    }
    lastMessageSentAtRef.current = Date.now();
    setIdleLong(false);
    setLoading(true);
    getSessionMessages(sessionId)
      .then(setMessages)
      .catch(() => setMessages([]))
      .finally(() => setLoading(false));
  }, [sessionId]);

  // Check periodically: if user hasn't sent for 2 min, show sleepy avatar
  useEffect(() => {
    if (!sessionId) return;
    sleepyCheckRef.current = setInterval(() => {
      if (sending || isAISpeaking) return;
      const last = lastMessageSentAtRef.current;
      if (last > 0 && Date.now() - last >= SLEEPY_IDLE_MS) setIdleLong(true);
    }, 20000);
    return () => {
      if (sleepyCheckRef.current) clearInterval(sleepyCheckRef.current);
      sleepyCheckRef.current = null;
    };
  }, [sessionId, sending, isAISpeaking]);

  const displayName = getDisplayName(user);
  const dashboardWelcome = displayName
    ? `Hi, ${displayName}. ${WELCOME_DASHBOARD_BASE}`
    : WELCOME_DASHBOARD_BASE;
  const newChatWelcome =
    sessionId && !loading && messages.length === 0
      ? displayName
        ? `Welcome, ${displayName}! ${WELCOME_NEW_CHAT_BASE}`
        : `Welcome! ${WELCOME_NEW_CHAT_BASE}`
      : null;

  function getTopK(): number | undefined {
    if (typeof window === "undefined") return undefined;
    const saved = localStorage.getItem("rag_top_k");
    if (saved === null) return undefined;
    const n = parseInt(saved, 10);
    return Number.isNaN(n) || n < 1 || n > 100 ? undefined : n;
  }

  async function handleAddToCart(product: ProductSummary) {
    try {
      await addItem({
        product_id: product.product_id,
        subject: product.subject,
        unit_price: product.price,
        image_url: product.image_url,
        category_name: product.category_name || "",
        variant_label: "",
        quantity: 1,
      });
    } catch {
      // toast in CartContext
    }
  }

  function clearProductMotionTimers() {
    if (productExpandRafRef.current != null) {
      cancelAnimationFrame(productExpandRafRef.current);
      productExpandRafRef.current = null;
    }
    if (productCloseTimerRef.current != null) {
      clearTimeout(productCloseTimerRef.current);
      productCloseTimerRef.current = null;
    }
  }

  function openProductSidebar(product: ProductSummary) {
    clearProductMotionTimers();
    const alreadyExpanded = sidebarWidthOpen && !!(sidebarProduct || closingProduct);
    setClosingProduct(null);
    setSidebarProduct(product);
    if (alreadyExpanded) {
      setSidebarWidthOpen(true);
      return;
    }
    // Mount at width 0, then expand next frames (same pattern as cart)
    setSidebarWidthOpen(false);
    productExpandRafRef.current = requestAnimationFrame(() => {
      productExpandRafRef.current = requestAnimationFrame(() => {
        setSidebarWidthOpen(true);
        productExpandRafRef.current = null;
      });
    });
  }

  function toggleProductSelection(product: ProductSummary) {
    setSelectedProducts((prev) => {
      const exists = prev.some((p) => p.product_id === product.product_id);
      if (exists) {
        if (sidebarProduct?.product_id === product.product_id) startCloseSidebar();
        else setSidebarProduct((current) => (current?.product_id === product.product_id ? null : current));
        return prev.filter((p) => p.product_id !== product.product_id);
      }
      openProductSidebar(product);
      return [...prev, product];
    });
  }

  function startCloseSidebar() {
    if (!sidebarProduct && !closingProduct) return;
    clearProductMotionTimers();
    if (sidebarProduct) setClosingProduct(sidebarProduct);
    setSidebarProduct(null);
    setSidebarWidthOpen(false);
    productCloseTimerRef.current = setTimeout(() => {
      setClosingProduct(null);
      productCloseTimerRef.current = null;
    }, PRODUCT_PANEL_MOTION_MS);
  }

  useEffect(() => {
    return () => clearProductMotionTimers();
  }, []);

  // Resize sidebar by dragging the left edge
  useEffect(() => {
    if (!isResizing) return;
    const onMove = (e: MouseEvent) => {
      const dx = e.clientX - resizeStartRef.current.x;
      const next = Math.min(SIDEBAR_WIDTH_MAX, Math.max(SIDEBAR_WIDTH_MIN, resizeStartRef.current.width - dx));
      setSidebarWidthPx(next);
    };
    const onUp = () => {
      setIsResizing(false);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    return () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isResizing]);

  function removeSelectedProduct(productId: number) {
    setSelectedProducts((prev) => prev.filter((p) => p.product_id !== productId));
    if (sidebarProduct?.product_id === productId) {
      startCloseSidebar();
    } else {
      setSidebarProduct((current) => (current?.product_id === productId ? null : current));
    }
  }

  async function handleSend(message: string, imageFile: File | null, attachedProducts?: ProductSummary[]) {
    if (!sessionId) return;
    lastMessageSentAtRef.current = Date.now();
    setIdleLong(false);
    const productsToAttach = attachedProducts ?? selectedProducts;
    const trimmedMessage = message.trim();
    const sidebarPayload = sidebarProduct ? buildSidebarProduct(sidebarProduct, sidebarVariant) : null;
    const userMessage: MessageEntry = {
      id: nextTempIdRef.current--,
      role: "user",
      content: trimmedMessage,
      image_url: imageFile ? URL.createObjectURL(imageFile) : null,
      attachedProducts: productsToAttach.length > 0 ? productsToAttach : undefined,
    };
    setMessages((prev) => [...prev, userMessage]);
    if (productsToAttach.length > 0) setSelectedProducts([]);
    
    // Use LLM-based intent detection (works for any language)
    setSending(true);
    try {
      const intentResult = await detectIntent(trimmedMessage, !!imageFile);
      setExpectsQdrantSearch(intentResult.needs_qdrant_search);
    } catch {
      // Fallback: assume search needed if detection fails
      setExpectsQdrantSearch(!!imageFile || trimmedMessage.length > 15);
    }
    
    try {
      const result = await sendChat(sessionId, trimmedMessage, imageFile, {
        topK: getTopK(),
        selectedProducts: productsToAttach,
        sidebarProduct: sidebarPayload,
      });
      const { message: responseText, products, suggested_emotion } = result;
      setMessages((prev) => [
        ...prev,
        {
          id: nextTempIdRef.current--,
          role: "assistant",
          content: responseText,
          image_url: null,
          products: products.length ? products : undefined,
        },
      ]);
      applySuggestedEmotion(suggested_emotion);
      const follow = commerceFollowUp(result);
      if (follow.refreshCart) await refresh();
      if (follow.orderToast) toast.success(follow.orderToast);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Message could not be sent.";
      toast.error(msg);
    } finally {
      setSending(false);
    }
  }

  async function handleSendVoice(voiceFile: File, attachedProducts?: ProductSummary[]) {
    if (!sessionId) return;
    lastMessageSentAtRef.current = Date.now();
    setIdleLong(false);
    // Use attached products from parameter or current selection
    const productsToAttach = attachedProducts ?? selectedProducts;
    const sidebarPayload = sidebarProduct ? buildSidebarProduct(sidebarProduct, sidebarVariant) : null;
    
    // Show user message with STT loader immediately
    const pendingUserMsgId = nextTempIdRef.current--;
    setSending(true);
    setMessages((prev) => [
      ...prev,
      {
        id: pendingUserMsgId,
        role: "user",
        content: "",
        image_url: null,
        attachedProducts: productsToAttach.length > 0 ? productsToAttach : undefined,
        transcribing: true,
      },
    ]);
    
    // STT + intent detection
    let transcribedText = "";
    try {
      const intentResult = await voiceDetectIntent(voiceFile);
      transcribedText = intentResult.transcribed_text || "";
      setExpectsQdrantSearch(productsToAttach.length > 0 || intentResult.needs_qdrant_search);
    } catch {
      setExpectsQdrantSearch(true);
    }
    
    // Replace loader with transcribed content in the same user message
    const userContent = transcribedText.trim() || "Voice message";
    setMessages((prev) =>
      prev.map((msg) =>
        msg.id === pendingUserMsgId
          ? { ...msg, content: userContent, transcribing: false }
          : msg
      )
    );
    
    // Clear selected products after capturing them
    if (productsToAttach.length > 0) setSelectedProducts([]);
    
    // Then: send voice chat for full response (with selected products)
    try {
      const result = await sendVoiceChat(
        sessionId,
        voiceFile,
        productsToAttach.length > 0 ? productsToAttach : undefined,
        sidebarPayload
      );
      const { message: responseText, products, audio_base64, suggested_emotion } = result;
      setMessages((prev) => [
        ...prev,
        {
          id: nextTempIdRef.current--,
          role: "assistant",
          content: responseText,
          image_url: null,
          products: products?.length ? products : undefined,
          audioBase64: audio_base64 ?? undefined,
        },
      ]);
      applySuggestedEmotion(suggested_emotion);
      const follow = commerceFollowUp(result);
      if (follow.refreshCart) await refresh();
      if (follow.orderToast) toast.success(follow.orderToast);
    } catch (err) {
      console.error("Voice message failed:", err);
      const errMsg = err instanceof Error ? err.message : "Voice message failed.";
      // Show more helpful error message based on error type
      let userMessage = "Sorry, voice message failed. Please try again or use text.";
      if (errMsg.includes("timeout") || errMsg.includes("fetch") || errMsg.includes("network")) {
        userMessage = "Connection timed out. The server may be busy. Please try again in a moment.";
      } else if (errMsg.includes("transcription") || errMsg.includes("speech")) {
        userMessage = "Could not understand the audio. Please speak clearly and try again.";
      }
      toast.error(errMsg);
      setMessages((prev) => [
        ...prev,
        {
          id: nextTempIdRef.current--,
          role: "assistant",
          content: userMessage,
          image_url: null,
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  const handleReadAloud = useCallback(async (text: string) => {
    if (!text?.trim() || !readAloudAudioRef.current) return;
    try {
      const { audio_base64 } = await readAloud(text);
      if (audio_base64 && readAloudAudioRef.current) {
        readAloudAudioRef.current.src = `data:audio/mpeg;base64,${audio_base64}`;
        await readAloudAudioRef.current.play();
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Read aloud failed");
    }
  }, []);

  function handleRegenerate() {
    const len = messages.length;
    if (len < 2) return;
    const lastUser = messages[len - 2];
    if (lastUser.role !== "user") return;
    setMessages((prev) => prev.slice(0, -2));
    handleSend(lastUser.content, null, lastUser.attachedProducts);
  }

  if (!sessionId) {
    return (
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-border/60 bg-card shadow-modern">
        <div className="flex-1 flex flex-col items-center justify-center text-center px-6">
          <div className="max-w-md space-y-4 animate-fade-in">
            <div className="w-12 h-12 mx-auto rounded-xl bg-muted flex items-center justify-center">
              <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-muted-foreground">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              </svg>
            </div>
            <h2 className="text-base font-medium text-foreground">Start a conversation</h2>
            {dashboardWelcome ? (
              <p className="text-foreground/90 text-sm leading-relaxed whitespace-pre-wrap">
                {dashboardWelcome}
              </p>
            ) : (
              <p className="text-muted-foreground text-sm">
                Select a chat or create a new one to begin.
              </p>
            )}
          </div>
        </div>
      </div>
    );
  }

  const avatarState: AIAvatarState = sending ? "thinking" : isAISpeaking ? "speaking" : "idle";
  const effectiveAvatarEmotion: AIAvatarEmotion =
    sending && sendingElapsedMs >= ANNOYED_THRESHOLD_MS
      ? "annoyed"
      : !sending && !isAISpeaking && idleLong
        ? "sleepy"
        : avatarEmotion;

  const productPanelOpen = !!(sidebarProduct || closingProduct);

  return (
    <div className="flex flex-row h-full flex-1 min-w-0 overflow-hidden">
      <audio
        ref={readAloudAudioRef}
        className="hidden"
        aria-hidden
        onPlay={handleAudioPlayStart}
        onEnded={handleAudioPlayEnd}
      />
      <div className="flex-1 min-w-0 flex flex-col overflow-hidden rounded-xl border border-border/60 bg-card shadow-modern">
        <div className="flex-1 min-h-0 flex flex-col w-full max-w-4xl mx-auto px-6 sm:px-8">
          <div className="flex-1 min-h-0 flex flex-col">
            {loading ? (
              <div className="flex-1 flex flex-col gap-6 py-6">
                <div className="flex gap-3 max-w-[85%]">
                  <Skeleton className="h-8 w-8 shrink-0 rounded-full" />
                  <div className="space-y-2 flex-1">
                    <Skeleton className="h-4 w-3/4" />
                    <Skeleton className="h-4 w-1/2" />
                  </div>
                </div>
                <div className="flex gap-3 max-w-[85%] ml-auto flex-row-reverse">
                  <Skeleton className="h-8 w-8 shrink-0 rounded-full" />
                  <div className="space-y-2 flex-1">
                    <Skeleton className="h-4 w-2/3 ml-auto" />
                    <Skeleton className="h-4 w-1/3 ml-auto" />
                  </div>
                </div>
                <div className="flex gap-3 max-w-[85%]">
                  <Skeleton className="h-8 w-8 shrink-0 rounded-full" />
                  <div className="space-y-2 flex-1">
                    <Skeleton className="h-4 w-full" />
                    <Skeleton className="h-4 w-4/5" />
                    <Skeleton className="h-4 w-1/2" />
                  </div>
                </div>
              </div>
            ) : (
              <MessageList
                messages={messages}
                sending={sending}
                expectsQdrantSearch={expectsQdrantSearch}
                welcomeMessage={newChatWelcome}
                suggestedPrompts={messages.length === 0 ? SUGGESTED_PROMPTS : undefined}
                onSuggestedPromptClick={(text) => void handleSend(text, null)}
                onRegenerate={handleRegenerate}
                selectedProductIds={new Set(selectedProducts.map((p) => p.product_id))}
                onProductSelect={toggleProductSelection}
                onAddToCart={handleAddToCart}
                voiceAudioRef={voiceAudioRef}
                onAudioPlayStart={handleAudioPlayStart}
                onAudioPlayEnd={handleAudioPlayEnd}
                onReadAloud={handleReadAloud}
                avatarState={avatarState}
                avatarEmotion={effectiveAvatarEmotion}
                onAvatarClick={handleAvatarClick}
                userAvatarUrl={user?.avatar_url ? getAvatarUrl(user.avatar_url) : null}
              />
            )}
          </div>
        </div>
        <div className="shrink-0 w-full max-w-4xl mx-auto px-6 sm:px-8">
          <MessageInput
            ref={messageInputRef}
            disabled={loading}
            sending={sending}
            onSend={handleSend}
            onSendVoice={handleSendVoice}
            attachedProducts={selectedProducts}
            onRemoveProduct={removeSelectedProduct}
            isAISpeaking={isAISpeaking}
            onStopAIPlayback={stopAIPlayback}
          />
        </div>
      </div>
      {productPanelOpen && (
        <div
          className={cn(
            "relative shrink-0 h-full overflow-hidden",
            isResizing
              ? "transition-none"
              : "transition-[width,margin-inline-start] duration-200 ease-linear",
            sidebarWidthOpen ? "ms-2 sm:ms-3" : "ms-0"
          )}
          style={{ width: sidebarWidthOpen ? sidebarWidthPx : 0 }}
          aria-hidden={!sidebarWidthOpen}
        >
          <div
            className="relative flex h-full min-w-0 flex-col overflow-hidden rounded-xl border border-border/60 bg-card shadow-modern"
            style={{ width: sidebarWidthPx }}
          >
            <div
              role="separator"
              aria-label="Resize sidebar"
              className="absolute inset-y-3 left-0 z-10 w-1.5 cursor-col-resize rounded-full bg-transparent hover:bg-primary/20 active:bg-primary/30 transition-colors"
              onMouseDown={(e) => {
                e.preventDefault();
                resizeStartRef.current = { x: e.clientX, width: sidebarWidthPx };
                setIsResizing(true);
              }}
            />
            <ProductSidebar
              product={sidebarProduct ?? closingProduct!}
              onClose={startCloseSidebar}
              onVariantChange={handleSidebarVariant}
            />
          </div>
        </div>
      )}
    </div>
  );
}
