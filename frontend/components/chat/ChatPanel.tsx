"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { TrendingUp, Search, ShoppingCart, CreditCard } from "lucide-react";
import { MessageList, type MessageEntry, type SuggestedPromptItem } from "./MessageList";
import { MessageInput, type MessageInputHandle } from "./MessageInput";
import { Skeleton } from "@/components/ui/skeleton";
import { getCurrentUser, getSessionMessages, sendChat, sendVoiceChat, detectIntent, voiceDetectIntent, type ProductSummary, type UserProfile } from "@/lib/api";

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

type Props = {
  sessionId: number | null;
};

function formatProductContext(products: ProductSummary[]): string {
  if (products.length === 0) return "";
  const lines = products.map((p) => {
    const parts = [`Name: ${p.subject}`];
    if (p.price != null) parts.push(`Price: ${typeof p.price === "number" ? p.price.toFixed(2) : p.price}`);
    if (p.category_name) parts.push(`Category: ${p.category_name}`);
    return `- ${parts.join(" | ")}`;
  });
  return `[Selected product(s) context:\n${lines.join("\n")}\n]\n\n`;
}

export function ChatPanel({ sessionId }: Props) {
  const [messages, setMessages] = useState<MessageEntry[]>([]);
  const [selectedProducts, setSelectedProducts] = useState<ProductSummary[]>([]);
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
  const audioEndDelayRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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
  }, []);

  useEffect(() => {
    return () => {
      if (audioEndDelayRef.current) clearTimeout(audioEndDelayRef.current);
    };
  }, []);

  useEffect(() => {
    getCurrentUser().then(setUser);
  }, []);

  // Focus input when entering chat (session ready, not loading)
  useEffect(() => {
    if (sessionId && !loading) {
      const t = setTimeout(() => messageInputRef.current?.focus(), 100);
      return () => clearTimeout(t);
    }
  }, [sessionId, loading]);

  // Focus input when model finishes responding
  const prevSending = useRef(sending);
  useEffect(() => {
    if (prevSending.current && !sending) {
      messageInputRef.current?.focus();
    }
    prevSending.current = sending;
  }, [sending]);

  useEffect(() => {
    if (!sessionId) {
      setMessages([]);
      return;
    }
    setLoading(true);
    getSessionMessages(sessionId)
      .then(setMessages)
      .catch(() => setMessages([]))
      .finally(() => setLoading(false));
  }, [sessionId]);

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

  function toggleProductSelection(product: ProductSummary) {
    setSelectedProducts((prev) => {
      const exists = prev.some((p) => p.product_id === product.product_id);
      if (exists) return prev.filter((p) => p.product_id !== product.product_id);
      return [...prev, product];
    });
  }

  function removeSelectedProduct(productId: number) {
    setSelectedProducts((prev) => prev.filter((p) => p.product_id !== productId));
  }

  async function handleSend(message: string, imageFile: File | null, attachedProducts?: ProductSummary[]) {
    if (!sessionId) return;
    const productsToAttach = attachedProducts ?? selectedProducts;
    const effectiveMessage = productsToAttach.length > 0 ? formatProductContext(productsToAttach) + message.trim() : message;
    const trimmedMessage = message.trim();
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
      const { message: responseText, products } = await sendChat(
        sessionId,
        effectiveMessage,
        imageFile,
        { topK: getTopK() }
      );
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
    } catch {
      // Error handling - could show a toast here
    } finally {
      setSending(false);
    }
  }

  async function handleSendVoice(voiceFile: File, attachedProducts?: ProductSummary[]) {
    if (!sessionId) return;
    
    // Use attached products from parameter or current selection
    const productsToAttach = attachedProducts ?? selectedProducts;
    
    // First: transcribe and detect intent (to show appropriate loader)
    setSending(true);
    let transcribedText = "";
    try {
      const intentResult = await voiceDetectIntent(voiceFile);
      transcribedText = intentResult.transcribed_text || "";
      // If products are attached, always expect Qdrant search (user is asking about specific products)
      setExpectsQdrantSearch(productsToAttach.length > 0 || intentResult.needs_qdrant_search);
    } catch {
      // Fallback: assume search needed if detection fails
      setExpectsQdrantSearch(true);
    }
    
    // Clear selected products after capturing them
    if (productsToAttach.length > 0) setSelectedProducts([]);
    
    // Then: send voice chat for full response (with selected products)
    try {
      const { message: responseText, products, audio_base64, transcribed_text } = await sendVoiceChat(
        sessionId,
        voiceFile,
        productsToAttach.length > 0 ? productsToAttach : undefined
      );
      const userContent = (transcribed_text && transcribed_text.trim()) ? transcribed_text.trim() : (transcribedText || "Voice message");
      setMessages((prev) => [
        ...prev,
        {
          id: nextTempIdRef.current--,
          role: "user",
          content: userContent,
          image_url: null,
          // Show attached products in user message bubble
          attachedProducts: productsToAttach.length > 0 ? productsToAttach : undefined,
        },
        {
          id: nextTempIdRef.current--,
          role: "assistant",
          content: responseText,
          image_url: null,
          products: products?.length ? products : undefined,
          audioBase64: audio_base64 ?? undefined,
        },
      ]);
    } catch (err) {
      console.error("Voice message failed:", err);
      setMessages((prev) => [
        ...prev,
        {
          id: nextTempIdRef.current--,
          role: "assistant",
          content: "Sorry, voice message failed. Please try again or use text.",
          image_url: null,
        },
      ]);
    } finally {
      setSending(false);
    }
  }

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
    );
  }

  return (
    <div className="flex flex-col h-full flex-1 min-w-0">
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
              voiceAudioRef={voiceAudioRef}
              onAudioPlayStart={handleAudioPlayStart}
              onAudioPlayEnd={handleAudioPlayEnd}
            />
          )}
        </div>
        <div className="shrink-0">
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
    </div>
  );
}
