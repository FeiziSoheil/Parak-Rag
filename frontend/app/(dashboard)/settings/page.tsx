"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { isAuthenticated } from "@/lib/auth";
import {
  getSettings,
  triggerIngest,
  triggerStoreFaqIngest,
  stopIngest,
  getIngestStatus,
  type IngestStatus,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import Link from "next/link";

const RAG_TOP_K_KEY = "rag_top_k";
const INGEST_LIMIT_KEY = "ingest_limit";

export default function SettingsPage() {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [serverTopK, setServerTopK] = useState<number | null>(null);
  const [topK, setTopK] = useState("");
  const [ingestLimit, setIngestLimit] = useState("");
  const [ingestLoading, setIngestLoading] = useState(false);
  const [ingestMessage, setIngestMessage] = useState<string | null>(null);
  const [storeFaqLoading, setStoreFaqLoading] = useState(false);
  const [storeFaqMessage, setStoreFaqMessage] = useState<string | null>(null);
  const [logOpen, setLogOpen] = useState(false);
  const [logStatus, setLogStatus] = useState<IngestStatus | null>(null);
  const [logLoading, setLogLoading] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;
    if (!isAuthenticated()) {
      router.replace("/login");
      return;
    }
    getSettings()
      .then((s) => {
        setServerTopK(s.rag_top_k);
        const saved = typeof window !== "undefined" ? localStorage.getItem(RAG_TOP_K_KEY) : null;
        setTopK(saved !== null ? saved : String(s.rag_top_k));
      })
      .catch(() => setServerTopK(5));
    getIngestStatus()
      .then(setLogStatus)
      .catch(() => {});
    const savedLimit = typeof window !== "undefined" ? localStorage.getItem(INGEST_LIMIT_KEY) : null;
    if (savedLimit) setIngestLimit(savedLimit);
  }, [mounted, router]);

  function handleSaveTopK() {
    const n = parseInt(topK, 10);
    if (Number.isNaN(n) || n < 1 || n > 100) {
      toast.error("Enter a number between 1 and 100");
      return;
    }
    if (typeof window !== "undefined") localStorage.setItem(RAG_TOP_K_KEY, String(n));
    setTopK(String(n));
    toast.success("RAG Top K saved");
  }

  function handleIngestLimitChange(v: string) {
    setIngestLimit(v);
    if (typeof window !== "undefined") {
      if (v.trim() === "") localStorage.removeItem(INGEST_LIMIT_KEY);
      else localStorage.setItem(INGEST_LIMIT_KEY, v);
    }
  }

  async function handleRunIngest() {
    setIngestMessage(null);
    setIngestLoading(true);
    try {
      const limit = ingestLimit.trim() ? parseInt(ingestLimit, 10) : undefined;
      if (ingestLimit.trim() && (Number.isNaN(limit!) || limit! < 1)) {
        return;
      }
      await triggerIngest(limit);
      setIngestMessage("Operation started");
      setLogOpen(true);
      setLogStatus({
        status: "running",
        count: null,
        limit: limit ?? null,
        finished_at: null,
        total: null,
        current_index: null,
        current_subject: null,
      });
      toast.success("Ingestion started");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Error starting ingestion";
      setIngestMessage(msg);
      toast.error(msg);
    } finally {
      setIngestLoading(false);
    }
  }

  async function handleStopIngest() {
    setIngestMessage(null);
    try {
      await stopIngest();
      setIngestMessage("Stopping…");
      toast.success("Stopping ingestion…");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Error stopping ingestion";
      setIngestMessage(msg);
      toast.error(msg);
    }
  }

  async function handleRunStoreFaqIngest() {
    setStoreFaqMessage(null);
    setStoreFaqLoading(true);
    try {
      await triggerStoreFaqIngest();
      setStoreFaqMessage("Store & FAQ ingestion started. Data is synced to SQLite and embedded into Qdrant.");
      toast.success("Store & FAQ ingestion started");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Error starting store/FAQ ingestion";
      setStoreFaqMessage(msg);
      toast.error(msg);
    } finally {
      setStoreFaqLoading(false);
    }
  }

  async function handleToggleLog() {
    if (logOpen) {
      setLogOpen(false);
      return;
    }
    setLogOpen(true);
    setLogLoading(true);
    try {
      const s = await getIngestStatus();
      setLogStatus(s);
    } catch {
      setLogStatus(null);
    } finally {
      setLogLoading(false);
    }
  }

  useEffect(() => {
    if (logStatus?.status !== "running") return;
    const interval = setInterval(async () => {
      try {
        const s = await getIngestStatus();
        setLogStatus(s);
      } catch {
        // ignore
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [logStatus?.status]);

  async function handleRefreshLog() {
    setLogLoading(true);
    try {
      const s = await getIngestStatus();
      setLogStatus(s);
    } catch {
      setLogStatus(null);
    } finally {
      setLogLoading(false);
    }
  }

  if (!mounted) {
    return (
      <div className="h-screen flex items-center justify-center bg-background relative overflow-hidden">
        <div className="gradient-mesh" aria-hidden />
        <div className="grain" aria-hidden />
        <div className="relative z-10 flex items-center gap-3">
          <div className="h-2 w-2 bg-primary rounded-full animate-pulse" />
          <span className="text-muted-foreground text-sm">Loading…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col bg-background relative overflow-hidden">
      <div className="gradient-mesh" aria-hidden />
      <div className="grain" aria-hidden />
      <div className="relative z-10 min-h-screen flex flex-col">
        <header className="shrink-0 border-b border-border px-5 py-3 flex items-center gap-3">
          <Link
            href="/chat"
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            ← Chat
          </Link>
          <h1 className="font-medium text-foreground text-sm">Settings</h1>
        </header>
        <main className="flex-1 p-6 max-w-xl mx-auto w-full">
          <div className="space-y-5">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">RAG Top K</CardTitle>
                <p className="text-sm text-muted-foreground font-normal mt-0.5">
                  Max similar results per query (default: {serverTopK ?? "—"})
                </p>
              </CardHeader>
              <CardContent className="space-y-2 pt-0">
                <div className="flex gap-2 items-center">
                  <Input
                    type="number"
                    min={1}
                    max={100}
                    value={topK}
                    onChange={(e) => setTopK(e.target.value)}
                    placeholder={String(serverTopK ?? 5)}
                    className="w-24 h-9"
                  />
                  <Button onClick={handleSaveTopK} size="sm">Save</Button>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Store & FAQ Ingestion</CardTitle>
                <p className="text-sm text-muted-foreground font-normal mt-0.5">
                  Sync <code className="text-xs bg-muted px-1 rounded">data/store.json</code> and{" "}
                  <code className="text-xs bg-muted px-1 rounded">data/faq.json</code> to SQLite, then embed into Qdrant (store + faq collections).
                </p>
              </CardHeader>
              <CardContent className="space-y-3 pt-0">
                <div className="flex gap-2 items-center flex-wrap">
                  <Button
                    onClick={handleRunStoreFaqIngest}
                    disabled={storeFaqLoading || logStatus?.status === "running"}
                    size="sm"
                  >
                    {storeFaqLoading ? "Starting…" : "Run store & FAQ ingestion"}
                  </Button>
                </div>
                {storeFaqMessage && (
                  <p className={`text-sm ${storeFaqMessage.startsWith("Error") ? "text-destructive" : "text-muted-foreground"}`}>
                    {storeFaqMessage}
                  </p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Product Data Ingestion</CardTitle>
                <p className="text-sm text-muted-foreground font-normal mt-0.5">
                  Max products to embed per run. Leave empty for all.
                </p>
                <p className="text-xs text-muted-foreground font-normal mt-1.5">
                  Approximate duration: ~1–3 min (GPU) or ~3–8 min (CPU) for 15 products; ~30–60 min (GPU) or ~1.5–3 h (CPU) for 500. First run includes model load (~15–60 s).
                </p>
              </CardHeader>
              <CardContent className="space-y-3 pt-0">
                <div className="flex gap-2 items-center flex-wrap">
                  <Input
                    id="ingest-limit"
                    type="number"
                    min={1}
                    value={ingestLimit}
                    onChange={(e) => handleIngestLimitChange(e.target.value)}
                    placeholder="All"
                    className="w-28 h-9"
                    disabled={logStatus?.status === "running"}
                  />
                  {logStatus?.status === "running" ? (
                    <Button
                      onClick={handleStopIngest}
                      variant="destructive"
                      size="sm"
                      className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                    >
                      Stop embedding
                    </Button>
                  ) : (
                    <Button
                      onClick={handleRunIngest}
                      disabled={ingestLoading}
                      size="sm"
                    >
                      {ingestLoading ? "Starting…" : "Run ingestion"}
                    </Button>
                  )}
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleToggleLog}
                    disabled={logLoading}
                  >
                    {logOpen ? "Hide log" : "Show log"}
                  </Button>
                </div>
                {ingestMessage && (
                  <p className={`text-sm ${ingestMessage.startsWith("Error") ? "text-destructive" : "text-muted-foreground"}`}>
                    {ingestMessage}
                  </p>
                )}
                {logOpen && (
                  <div className="rounded-md border border-border bg-muted/50 p-3 text-sm">
                    <p className="font-medium text-foreground mb-1">Ingestion Status</p>
                    {logLoading ? (
                      <p className="text-muted-foreground">Loading…</p>
                    ) : logStatus === null ? (
                      <p className="text-muted-foreground">Could not load status.</p>
                    ) : logStatus.status === "running" ? (
                      <div className="space-y-1 text-muted-foreground">
                        <p>
                          Embedding product <strong>{logStatus.current_index ?? 0}</strong> of{" "}
                          <strong>{logStatus.total ?? "—"}</strong>
                        </p>
                        {logStatus.current_subject && (
                          <p className="text-xs truncate" title={logStatus.current_subject}>
                            Current: {logStatus.current_subject}
                          </p>
                        )}
                      </div>
                    ) : (
                      <p className="text-muted-foreground">
                        Points in collection: <strong>{logStatus.collection_count ?? logStatus.count ?? "—"}</strong>
                        {logStatus.limit != null && ` (last run limit: ${logStatus.limit})`}
                      </p>
                    )}
                    {logStatus?.log_lines && logStatus.log_lines.length > 0 && (
                      <div className="mt-2 rounded border border-border bg-background/80 overflow-hidden">
                        <p className="text-xs text-muted-foreground px-2 py-1 border-b border-border">Live log</p>
                        <pre
                          className="p-2 text-xs font-mono text-muted-foreground overflow-auto max-h-48 min-h-24 whitespace-pre-wrap break-words"
                          role="log"
                          aria-live="polite"
                        >
                          {logStatus.log_lines.join("\n")}
                        </pre>
                      </div>
                    )}
                    {!logLoading && logStatus !== null && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="mt-2"
                        onClick={handleRefreshLog}
                        disabled={logLoading}
                      >
                        Refresh
                      </Button>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </main>
      </div>
    </div>
  );
}
