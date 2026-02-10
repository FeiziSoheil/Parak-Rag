"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { isAuthenticated } from "@/lib/auth";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    if (isAuthenticated()) {
      router.replace("/chat");
    } else {
      router.replace("/login");
    }
  }, [router]);
  return (
    <div className="min-h-screen flex items-center justify-center bg-background relative overflow-hidden">
      <div className="gradient-mesh" aria-hidden />
      <div className="grain" aria-hidden />
      <div className="relative z-10 flex flex-col items-center gap-4 animate-fade-in">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary/20 to-accent/20 flex items-center justify-center animate-pulse">
          <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-primary">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
        </div>
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 bg-primary rounded-full animate-pulse" />
          <p className="text-muted-foreground text-sm">Redirecting…</p>
        </div>
      </div>
    </div>
  );
}
