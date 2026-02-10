"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { login } from "@/lib/api";
import { setToken } from "@/lib/auth";

export function LoginForm() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const data = await login(username, password);
      setToken((data as { access_token: string }).access_token);
      router.replace("/chat");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="w-full" style={{ minWidth: "320px", maxWidth: "380px" }}>
      <CardHeader className="space-y-1.5 pb-4">
        <CardTitle>Log in</CardTitle>
        <p className="text-sm text-muted-foreground font-normal">
          Enter your credentials to continue
        </p>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {error && (
            <p className="text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2">
              {error}
            </p>
          )}
          <div className="space-y-2">
            <Label htmlFor="username">Username</Label>
            <Input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoComplete="username"
              placeholder="Enter your username"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              placeholder="Enter your password"
            />
          </div>
          <Button type="submit" disabled={loading} className="h-9 mt-1">
            {loading ? "Logging in…" : "Log in"}
          </Button>
          <p className="text-center text-sm text-muted-foreground pt-1">
            Don&apos;t have an account?{" "}
            <Link href="/register" className="font-medium text-foreground hover:underline">
              Register
            </Link>
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
