// In the browser we use a relative path so requests go from the same origin and Next.js proxies them to the backend (no CORS).
const API_BASE = typeof window === "undefined" ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000" : "";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

export type UserProfile = {
  id: number;
  username: string;
  email?: string | null;
  email_verified?: boolean;
  first_name?: string | null;
  last_name?: string | null;
  avatar_url?: string | null;
};

export async function getCurrentUser(): Promise<UserProfile | null> {
  const token = getToken();
  if (!token) return null;
  const res = await fetch(`${API_BASE}/api/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return null;
  return res.json();
}

export function getAvatarUrl(avatarUrl: string | null | undefined): string | null {
  if (!avatarUrl?.trim()) return null;
  const u = avatarUrl.trim();
  if (u.startsWith("http")) return u;
  return `${API_BASE}${u.startsWith("/") ? "" : "/"}${u}`;
}

export async function updateProfile(data: { first_name?: string; last_name?: string }): Promise<UserProfile> {
  const token = getToken();
  if (!token) throw new Error("Not authenticated");
  const res = await fetch(`${API_BASE}/api/auth/me`, {
    method: "PATCH",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Update failed");
  }
  return res.json();
}

export async function uploadAvatar(file: File): Promise<UserProfile> {
  const token = getToken();
  if (!token) throw new Error("Not authenticated");
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/auth/avatar`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Upload failed");
  }
  return res.json();
}

export async function requestEmailChange(new_email: string): Promise<{ message: string }> {
  const token = getToken();
  if (!token) throw new Error("Not authenticated");
  const res = await fetch(`${API_BASE}/api/auth/request-email-change`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ new_email }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed");
  }
  return res.json();
}

export async function confirmEmailChange(token: string): Promise<{ message: string }> {
  const t = getToken();
  if (!t) throw new Error("Not authenticated");
  const res = await fetch(`${API_BASE}/api/auth/confirm-email-change?token=${encodeURIComponent(token)}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed");
  }
  return res.json();
}

export async function requestPasswordChange(): Promise<{ message: string }> {
  const token = getToken();
  if (!token) throw new Error("Not authenticated");
  const res = await fetch(`${API_BASE}/api/auth/request-password-change`, { method: "POST", headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed");
  }
  return res.json();
}

export async function confirmPasswordChange(code: string, new_password: string): Promise<{ message: string }> {
  const token = getToken();
  if (!token) throw new Error("Not authenticated");
  const res = await fetch(`${API_BASE}/api/auth/confirm-password-change`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ code, new_password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed");
  }
  return res.json();
}

export async function login(username: string, password: string) {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Login failed");
  }
  return res.json();
}

export async function register(username: string, email: string, password: string) {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Registration failed");
  }
  return res.json();
}

export async function verifyEmail(token: string): Promise<{ message: string }> {
  const res = await fetch(`${API_BASE}/api/auth/verify-email?token=${encodeURIComponent(token)}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Verification failed");
  }
  return res.json();
}

export async function verifyEmailByCode(email: string, code: string): Promise<{ message: string }> {
  const res = await fetch(`${API_BASE}/api/auth/verify-email-by-code`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, code }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Verification failed");
  }
  return res.json();
}

export async function resendVerificationEmail(email: string): Promise<{ message: string }> {
  const res = await fetch(`${API_BASE}/api/auth/resend-verification`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed to resend");
  }
  return res.json();
}

export async function getWelcome(type: "dashboard" | "new_chat"): Promise<{ text: string }> {
  const token = getToken();
  if (!token) throw new Error("Not authenticated");
  const res = await fetch(`${API_BASE}/api/welcome?type=${type}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to load welcome");
  return res.json();
}

export async function listSessions(): Promise<{ id: number; title: string; created_at: string }[]> {
  const token = getToken();
  if (!token) throw new Error("Not authenticated");
  const res = await fetch(`${API_BASE}/api/sessions`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to load sessions");
  return res.json();
}

export async function createSession(title?: string): Promise<{ id: number; title: string; created_at: string }> {
  const token = getToken();
  if (!token) throw new Error("Not authenticated");
  const res = await fetch(`${API_BASE}/api/sessions`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ title: title || "New Chat" }),
  });
  if (!res.ok) throw new Error("Failed to create session");
  return res.json();
}

export async function deleteSession(sessionId: number): Promise<void> {
  const token = getToken();
  if (!token) throw new Error("Not authenticated");
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to delete session");
}

export type ProductVariantAttribute = {
  name?: string;
  value?: string;
};

export type ProductVariant = {
  name?: string;
  color?: string;
  price?: number | null;
  /** Variant image URL (e.g. color/size specific). */
  image?: string | null;
  /** Attributes from backend (e.g. Color: Red, Size: M). Each has name + value. */
  attributes?: ProductVariantAttribute[];
};

export type ProductSummary = {
  product_id: number;
  subject: string;
  price: number | null;
  image_url: string | null;
  category_name: string;
  /** Product variants (colors, sizes, etc.) with their prices */
  variants?: ProductVariant[];
};

/** We use a proxy for product images so CDNs (e.g. AliExpress) don't block the image. */
export function getProductImageUrl(url: string | null | undefined): string | null {
  if (!url?.trim()) return null;
  const u = url.trim();
  if (u.startsWith("http://") || u.startsWith("https://")) {
    return `${API_BASE}/api/proxy-image?url=${encodeURIComponent(u)}`;
  }
  return u;
}

export async function getSessionMessages(
  sessionId: number
): Promise<{ id: number; role: string; content: string; image_url: string | null; products?: ProductSummary[]; created_at: string }[]> {
  const token = getToken();
  if (!token) throw new Error("Not authenticated");
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/messages`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to load messages");
  return res.json();
}

export type MessageSearchResult = {
  message_id: number;
  session_id: number;
  session_title: string;
  role: string;
  content_snippet: string;
  created_at: string;
};

export async function searchSessionMessages(q: string): Promise<MessageSearchResult[]> {
  const token = getToken();
  if (!token) throw new Error("Not authenticated");
  const res = await fetch(`${API_BASE}/api/sessions/search?q=${encodeURIComponent(q.trim())}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to search sessions");
  return res.json();
}

export type RagSettings = {
  rag_top_k: number;
  rag_score_threshold: number;
};

export async function getSettings(): Promise<RagSettings> {
  const token = getToken();
  if (!token) throw new Error("Not authenticated");
  const res = await fetch(`${API_BASE}/api/settings`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to load settings");
  return res.json();
}

/** Trigger ingestion (requires auth or X-Api-Key). limit = max products to ingest; omit for all. */
export async function triggerIngest(limit?: number): Promise<{ status: string; data_dir: string; limit: number | null }> {
  const token = getToken();
  if (!token) throw new Error("Not authenticated");
  const path = `${API_BASE}/api/ingest`;
  const query = limit != null && limit > 0 ? `?limit=${limit}` : "";
  const res = await fetch(path + query, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Ingest failed");
  }
  return res.json();
}

/** Trigger store & FAQ ingestion: sync JSON → SQLite → embed → Qdrant (store + faq collections). Requires auth or X-Api-Key. */
export async function triggerStoreFaqIngest(): Promise<{ status: string; store_json: string; faq_json: string }> {
  const token = getToken();
  if (!token) throw new Error("Not authenticated");
  const res = await fetch(`${API_BASE}/api/ingest/store-faq`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Store/FAQ ingest failed");
  }
  return res.json();
}

/** Request running ingestion to stop (requires auth or X-Api-Key). */
export async function stopIngest(): Promise<{ status: string }> {
  const token = getToken();
  if (!token) throw new Error("Not authenticated");
  const res = await fetch(`${API_BASE}/api/ingest/stop`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Stop ingest failed");
  }
  return res.json();
}

export type IngestStatus = {
  status: "running" | "idle";
  count: number | null;
  limit: number | null;
  finished_at: string | null;
  total: number | null;
  current_index: number | null;
  current_subject: string | null;
  /** When idle: actual points count in Qdrant collection (so UI shows e.g. 15 products). */
  collection_count?: number | null;
  /** Live log lines from current/last run (timestamped). */
  log_lines?: string[];
};

export async function getIngestStatus(): Promise<IngestStatus> {
  const token = getToken();
  if (!token) throw new Error("Not authenticated");
  const res = await fetch(`${API_BASE}/api/ingest/status`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to load ingest status");
  return res.json();
}

export type DetectIntentResult = {
  needs_qdrant_search: boolean;
  intent_type: "product_search" | "store_info" | "faq" | "chitchat" | "greeting" | "unknown";
  confidence: number;
};

export type VoiceDetectIntentResult = DetectIntentResult & {
  transcribed_text: string;
};

/**
 * Detect user intent using LLM. Call before sendChat to show appropriate loading indicator.
 * Works for any language without hardcoded keywords.
 */
export async function detectIntent(message: string, hasImage: boolean = false): Promise<DetectIntentResult> {
  const token = getToken();
  if (!token) throw new Error("Not authenticated");
  const formData = new FormData();
  formData.append("message", message);
  formData.append("has_image", String(hasImage));
  const res = await fetch(`${API_BASE}/api/detect-intent`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });
  if (!res.ok) {
    // Fallback: assume search needed on error
    return { needs_qdrant_search: true, intent_type: "unknown", confidence: 0.5 };
  }
  return res.json();
}

/**
 * Transcribe voice and detect intent using LLM.
 * Call before sendVoiceChat to show appropriate loading indicator.
 * Returns transcribed text + intent detection result.
 */
export async function voiceDetectIntent(voiceFile: File): Promise<VoiceDetectIntentResult> {
  const token = getToken();
  if (!token) throw new Error("Not authenticated");
  const formData = new FormData();
  formData.append("voice", voiceFile);
  const res = await fetch(`${API_BASE}/api/voice-detect-intent`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });
  if (!res.ok) {
    // Fallback: assume search needed on error
    return { transcribed_text: "", needs_qdrant_search: true, intent_type: "unknown", confidence: 0.5 };
  }
  return res.json();
}

export type SendChatResult = { message: string; products: ProductSummary[] };

export async function sendChat(
  sessionId: number,
  message: string,
  imageFile: File | null,
  options?: { topK?: number }
): Promise<SendChatResult> {
  const token = getToken();
  if (!token) throw new Error("Not authenticated");
  const formData = new FormData();
  formData.append("session_id", String(sessionId));
  formData.append("message", message);
  if (imageFile) formData.append("image", imageFile);
  if (options?.topK != null && options.topK > 0) formData.append("top_k", String(options.topK));
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Chat failed");
  }
  return res.json();
}

export type SendVoiceChatResult = {
  message: string;
  products: ProductSummary[];
  /** متن ترنسکریب‌شده از صدای کاربر (STT) */
  transcribed_text: string;
  audio_base64?: string;
};

export async function sendVoiceChat(
  sessionId: number,
  voiceFile: File,
  selectedProducts?: ProductSummary[]
): Promise<SendVoiceChatResult> {
  const token = getToken();
  if (!token) throw new Error("Not authenticated");
  const formData = new FormData();
  formData.append("session_id", String(sessionId));
  formData.append("voice", voiceFile);
  // Send selected products as JSON so backend knows which product(s) user is asking about
  if (selectedProducts && selectedProducts.length > 0) {
    formData.append("selected_products", JSON.stringify(selectedProducts));
  }
  const res = await fetch(`${API_BASE}/api/voice-chat`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Voice chat failed");
  }
  return res.json();
}
