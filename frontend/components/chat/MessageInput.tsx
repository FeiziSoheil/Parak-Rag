"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { AudioLines } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { ProductSummary } from "@/lib/api";
import { float32ToWavFile } from "@/lib/audioUtils";
import { playVoiceActivationSound } from "@/components/chat/VoiceActivationSound";
import { playVoiceDeactivationSound } from "@/components/chat/VoiceDeactivationSound";

export type MessageInputHandle = { focus: () => void };

export type VoiceUIState = "idle" | "listening" | "userSpeaking" | "processing" | "aiSpeaking";

type Props = {
  disabled?: boolean;
  /** True while a message (text or voice) is being sent. */
  sending?: boolean;
  onSend: (message: string, imageFile: File | null, attachedProducts?: ProductSummary[]) => Promise<void>;
  /** Voice handler now receives attached products so backend knows which product user is asking about */
  onSendVoice?: (voiceFile: File, attachedProducts?: ProductSummary[]) => Promise<void>;
  attachedProducts?: ProductSummary[];
  onRemoveProduct?: (productId: number) => void;
  /** When AI is playing voice response; VAD must be paused to avoid feedback loop. */
  isAISpeaking?: boolean;
  /** Call to stop AI playback (e.g. on user interruption). */
  onStopAIPlayback?: () => void;
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

function IconSquare({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="currentColor"
      className={className}
      aria-hidden
    >
      <rect width="14" height="14" x="5" y="5" rx="2" />
    </svg>
  );
}

/** Waveform bars for "AI Speaking" state. */
function IconWaveform({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="currentColor"
      className={className}
      aria-hidden
    >
      <rect x="3" y="8" width="2" height="8" rx="1" />
      <rect x="7" y="5" width="2" height="14" rx="1" />
      <rect x="11" y="9" width="2" height="6" rx="1" />
      <rect x="15" y="4" width="2" height="16" rx="1" />
      <rect x="19" y="7" width="2" height="10" rx="1" />
    </svg>
  );
}

const MIN_VOICE_SAMPLES = 1600; // ~0.1s at 16kHz (allow very short utterances)
// VAD assets from CDN (worklet + Silero ONNX). WASM from same-origin to avoid fetch/CORS errors.
const VAD_BASE_ASSET_PATH = "https://cdn.jsdelivr.net/npm/@ricky0123/vad-web@0.0.27/dist/";
// Serve onnxruntime-web from public/onnxruntime-web (copied by postinstall) so .mjs/.wasm load correctly
const VAD_ONNX_WASM_PATH = "/onnxruntime-web/";

const MessageInputInner = forwardRef<MessageInputHandle, Props>(function MessageInput(
  { disabled, sending: sendingProp = false, onSend, onSendVoice, attachedProducts = [], onRemoveProduct, isAISpeaking = false, onStopAIPlayback },
  ref
) {
  const [text, setText] = useState("");
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [sendingText, setSendingText] = useState(false);
  const [voiceModeActive, setVoiceModeActive] = useState(false);
  const [userSpeaking, setUserSpeaking] = useState(false);
  const [vadLoading, setVadLoading] = useState(false);
  const [vadError, setVadError] = useState<string | null>(null);
  const [inputFocused, setInputFocused] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const vadRef = useRef<{ pause: () => void; start: () => void | Promise<void> } | null>(null);
  // Keep a ref to attached products so VAD callback can access current value
  const attachedProductsRef = useRef<ProductSummary[]>(attachedProducts);
  attachedProductsRef.current = attachedProducts;
  const sending = sendingProp || sendingText;

  const hasContent = !!(text.trim() || imageFile || attachedProducts.length > 0);
  const showSendButton = inputFocused && hasContent;

  useImperativeHandle(ref, () => ({
    focus() {
      textareaRef.current?.focus();
    },
  }));

  // Auto-grow textarea height with content (single line by default, grow up to max)
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    const maxHeight = 112; // 7rem
    ta.style.height = `${Math.min(ta.scrollHeight, maxHeight)}px`;
  }, [text]);

  // Start or stop VAD when entering/leaving voice mode
  useEffect(() => {
    if (!voiceModeActive || !onSendVoice) {
      vadRef.current?.pause();
      vadRef.current = null;
      setVadLoading(false);
      setVadError(null);
      return;
    }
    let mounted = true;
    setVadError(null);
    setVadLoading(true);
    import("@ricky0123/vad-web").then(({ MicVAD }) => {
      if (!mounted || !voiceModeActive) return;
      MicVAD.new({
        baseAssetPath: VAD_BASE_ASSET_PATH,
        onnxWASMBasePath: VAD_ONNX_WASM_PATH,
        onSpeechStart: () => setUserSpeaking(true),
        onSpeechEnd: (audio: Float32Array) => {
          setUserSpeaking(false);
          if (audio.length < MIN_VOICE_SAMPLES) return;
          const file = float32ToWavFile(audio);
          // Pass attached products to voice handler so backend knows which product user is asking about
          const productsToSend = attachedProductsRef.current.length > 0 ? [...attachedProductsRef.current] : undefined;
          onSendVoice(file, productsToSend).catch((err) => console.error("Voice send failed:", err));
        },
        minSpeechMs: 300,
        redemptionMs: 1200,
        positiveSpeechThreshold: 0.2,
        negativeSpeechThreshold: 0.2,
      })
        .then(async (vad) => {
          if (!mounted || !voiceModeActive) {
            vad.pause();
            return;
          }
          vadRef.current = vad;
          setVadLoading(false);
          try {
            if (!sendingProp && !isAISpeaking) await vad.start();
          } catch (startErr) {
            console.error("VAD start failed:", startErr);
            if (mounted) setVadError((startErr as Error)?.message ?? "Microphone could not start");
          }
        })
        .catch((err) => {
          console.error("VAD init failed:", err);
          if (mounted) {
            setVadError(err?.message ?? "Microphone error");
            setVadLoading(false);
          }
        });
    }).catch((err) => {
      console.error("VAD import failed:", err);
      if (mounted) {
        setVadError(err?.message ?? "Voice detection load error");
        setVadLoading(false);
      }
    });
    return () => {
      mounted = false;
      vadRef.current?.pause();
      vadRef.current = null;
      setVadLoading(false);
    };
  }, [voiceModeActive, onSendVoice]);

  // Pause VAD when AI is speaking or when sending; resume when both clear
  useEffect(() => {
    const vad = vadRef.current;
    if (!vad) return;
    if (isAISpeaking || sendingProp) vad.pause();
    else if (voiceModeActive) {
      const p = vad.start();
      if (p instanceof Promise) p.catch((err: unknown) => console.error("VAD resume failed:", err));
    }
  }, [isAISpeaking, sendingProp, voiceModeActive]);

  const handleMicClick = useCallback(() => {
    if (voiceModeActive) {
      if (isAISpeaking) onStopAIPlayback?.();
      vadRef.current?.pause();
      vadRef.current = null;
      playVoiceDeactivationSound(); // Play descending sound when voice mode deactivates
      setVoiceModeActive(false);
      setUserSpeaking(false);
      setVadError(null);
    } else {
      if (!onSendVoice || disabled || sending) return;
      playVoiceActivationSound(); // Play chime when voice mode activates
      setVoiceModeActive(true);
    }
  }, [voiceModeActive, isAISpeaking, onStopAIPlayback, onSendVoice, disabled, sending]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const toSend = text.trim();
    if ((!toSend && !imageFile && attachedProducts.length === 0) || sending || disabled) return;
    const fileToSend = imageFile;
    const productsToSend = attachedProducts.length > 0 ? attachedProducts : undefined;
    setText("");
    setImageFile(null);
    setSendingText(true);
    try {
      await onSend(toSend || "(Image)", fileToSend, productsToSend);
    } finally {
      setSendingText(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      if (voiceModeActive) {
        e.preventDefault();
        setVoiceModeActive(false);
        setUserSpeaking(false);
        setVadError(null);
      }
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  }

  return (
    <div className="sticky bottom-0 left-0 right-0 p-3 sm:p-4 flex justify-center bg-background shadow-none">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-[min(100%,28rem)] focus-within:max-w-[min(100%,42rem)] bg-background/95 dark:bg-background/90 backdrop-blur-sm shadow-none p-3 sm:p-4 transition-[max-width] duration-300 ease-out"
      >
        {(attachedProducts.length > 0 || imageFile) && (
          <div className="mb-3 flex flex-wrap items-center gap-2 animate-slide-down">
            {attachedProducts.map((p) => (
              <div
                key={p.product_id}
                className="flex items-center gap-2 rounded-lg border border-border bg-muted/50 px-2.5 py-1.5 text-sm"
              >
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="max-w-[140px] truncate text-foreground cursor-default">
                      {p.subject}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent side="top">
                    <p>{p.subject}</p>
                  </TooltipContent>
                </Tooltip>
                {onRemoveProduct && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        onClick={() => onRemoveProduct(p.product_id)}
                        className="p-0.5 rounded text-muted-foreground hover:text-destructive transition-colors"
                        aria-label="Remove from attachment"
                      >
                        <IconClose />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top">
                      <p>Remove from attachment</p>
                    </TooltipContent>
                  </Tooltip>
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
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        onClick={() => setImageFile(null)}
                        className="absolute -top-1 -right-1 p-1 rounded bg-card border border-border text-muted-foreground hover:text-destructive transition-colors"
                        aria-label="Remove image"
                      >
                        <IconClose />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top">
                      <p>Remove image</p>
                    </TooltipContent>
                  </Tooltip>
                </div>
                <span className="text-xs text-muted-foreground">{imageFile.name}</span>
              </>
            )}
          </div>
        )}
        <div className="flex items-end py-1.5 px-2 gap-1 rounded-2xl border border-border bg-background focus-within:border-foreground/15 focus-within:ring-1 focus-within:ring-ring/15 transition-all overflow-hidden">
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => setImageFile(e.target.files?.[0] ?? null)}
        />
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={disabled || sending || voiceModeActive}
              className="flex items-center justify-center w-8 h-8 shrink-0 text-muted-foreground hover:text-foreground rounded-lg transition-colors disabled:opacity-50 disabled:pointer-events-none ml-0.5"
              aria-label="Attach image"
            >
              <IconImage />
            </button>
          </TooltipTrigger>
          <TooltipContent side="top">
            <p>Attach image</p>
          </TooltipContent>
        </Tooltip>
        <Textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onFocus={() => setInputFocused(true)}
          onBlur={() => setInputFocused(false)}
          onKeyDown={handleKeyDown}
          placeholder="Message… (Click / to focus)"
          rows={1}
          className="!min-h-[22px] max-h-28 resize-none flex-1 rounded-none border-0 bg-transparent shadow-none focus-visible:ring-0 focus-visible:ring-offset-0 py-1.5 px-2 text-sm placeholder:text-muted-foreground leading-tight"
          disabled={disabled || sending || voiceModeActive}
        />
        {showSendButton ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="submit"
                disabled={!hasContent || sending || disabled || voiceModeActive}
                className="flex items-center justify-center w-8 h-8 shrink-0 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:pointer-events-none mr-0.5"
                aria-label="Send message"
              >
                {sending ? (
                  <IconLoader className="text-primary-foreground size-4" />
                ) : (
                  <IconSend />
                )}
              </button>
            </TooltipTrigger>
            <TooltipContent side="top">
              <p>Send</p>
            </TooltipContent>
          </Tooltip>
        ) : onSendVoice ? (
          (() => {
            const voiceState: VoiceUIState = !voiceModeActive
              ? "idle"
              : vadError
                ? "idle"
                : sendingProp
                  ? "processing"
                  : isAISpeaking
                    ? "aiSpeaking"
                    : userSpeaking
                      ? "userSpeaking"
                      : "listening";
            const micTitle = vadError
              ? vadError + " (Click to dismiss)"
              : voiceState === "idle"
                ? "Turn on voice mode"
                : voiceState === "listening"
                  ? (vadLoading ? "Starting microphone…" : "Listening… Click to turn off")
                  : voiceState === "userSpeaking"
                    ? "Speaking… Click to turn off"
                    : voiceState === "processing"
                      ? "Sending…"
                      : "PARAK is speaking. Click to stop";
            return (
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={handleMicClick}
                    disabled={disabled || (sending && !voiceModeActive)}
                    className={`flex items-center justify-center w-8 h-8 shrink-0 rounded-xl transition-colors disabled:opacity-50 disabled:pointer-events-none mr-0.5 ${
                      vadError
                        ? "text-destructive bg-destructive/15 hover:bg-destructive/25"
                        : voiceState === "idle"
                          ? "text-muted-foreground hover:text-foreground"
                          : voiceState === "listening"
                            ? "text-destructive/80 bg-destructive/10 hover:bg-destructive/20"
                            : voiceState === "userSpeaking"
                              ? "text-destructive bg-destructive/20 hover:bg-destructive/30 animate-pulse"
                              : voiceState === "processing"
                                ? "text-muted-foreground bg-muted"
                                : "text-green-600 dark:text-green-500 bg-green-500/15 hover:bg-green-500/25"
                    }`}
                    aria-label={micTitle}
                  >
                    {vadLoading ? (
                      <IconLoader className="text-muted-foreground" />
                    ) : voiceState === "processing" ? (
                      <IconLoader className="text-muted-foreground" />
                    ) : voiceState === "aiSpeaking" ? (
                      <IconWaveform />
                    ) : voiceModeActive ? (
                      <IconSquare />
                    ) : (
                      <AudioLines className="size-4" />
                    )}
                  </button>
                </TooltipTrigger>
                <TooltipContent side="top">
                  <p>{micTitle}</p>
                </TooltipContent>
              </Tooltip>
            );
          })()
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="submit"
                disabled={!hasContent || sending || disabled}
                className="flex items-center justify-center w-8 h-8 shrink-0 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:pointer-events-none mr-0.5"
                aria-label="Send message"
              >
                {sending ? (
                  <IconLoader className="text-primary-foreground size-4" />
                ) : (
                  <IconSend />
                )}
              </button>
            </TooltipTrigger>
            <TooltipContent side="top">
              <p>Send</p>
            </TooltipContent>
          </Tooltip>
        )}
      </div>
    </form>
    </div>
  );
});

export { MessageInputInner as MessageInput };
