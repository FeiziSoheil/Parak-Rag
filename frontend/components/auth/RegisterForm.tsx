"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSeparator,
  InputOTPSlot,
} from "@/components/ui/input-otp";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { register, resendVerificationEmail, verifyEmailByCode } from "@/lib/api";

export function RegisterForm() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [registered, setRegistered] = useState(false);
  const [resendMessage, setResendMessage] = useState("");
  const [resendLoading, setResendLoading] = useState(false);
  const [code, setCode] = useState("");
  const [codeError, setCodeError] = useState("");
  const [codeSuccess, setCodeSuccess] = useState(false);
  const [codeLoading, setCodeLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await register(username, email, password);
      setRegistered(true);
      toast.success("Account created. Check your email to verify.");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Registration failed";
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }

  async function handleResend() {
    setResendMessage("");
    setResendLoading(true);
    try {
      const res = await resendVerificationEmail(email);
      setResendMessage(res.message);
      toast.success(res.message);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to resend";
      setResendMessage(msg);
      toast.error(msg);
    } finally {
      setResendLoading(false);
    }
  }

  async function handleVerifyByCode(e: React.FormEvent) {
    e.preventDefault();
    setCodeError("");
    setCodeLoading(true);
    try {
      await verifyEmailByCode(email, code);
      setCodeSuccess(true);
      toast.success("Email verified. You can log in now.");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Invalid or expired code";
      setCodeError(msg);
      toast.error(msg);
    } finally {
      setCodeLoading(false);
    }
  }

  if (registered) {
    return (
      <Card className="w-full" style={{ minWidth: "320px", maxWidth: "380px" }}>
        <CardHeader className="space-y-1.5 pb-4">
          <CardTitle>Check your email</CardTitle>
          <p className="text-sm text-muted-foreground font-normal">
            We sent a verification link and a 6-digit code to <strong>{email}</strong>. Click the link or enter the code below.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          {codeSuccess ? (
            <p className="text-sm text-green-600 dark:text-green-400">Email verified. You can log in now.</p>
          ) : (
            <form onSubmit={handleVerifyByCode} className="space-y-2">
              <Label>Verification code</Label>
              <div className="flex flex-col gap-3">
                <InputOTP
                  maxLength={6}
                  value={code}
                  onChange={setCode}
                >
                  <InputOTPGroup>
                    <InputOTPSlot index={0} />
                    <InputOTPSlot index={1} />
                  </InputOTPGroup>
                  <InputOTPSeparator />
                  <InputOTPGroup>
                    <InputOTPSlot index={2} />
                    <InputOTPSlot index={3} />
                  </InputOTPGroup>
                  <InputOTPSeparator />
                  <InputOTPGroup>
                    <InputOTPSlot index={4} />
                    <InputOTPSlot index={5} />
                  </InputOTPGroup>
                </InputOTP>
                <Button type="submit" disabled={codeLoading || code.length < 6}>
                  {codeLoading ? "Verifying…" : "Verify"}
                </Button>
              </div>
              {codeError && (
                <p className="text-sm text-destructive">{codeError}</p>
              )}
            </form>
          )}
          {resendMessage && (
            <p className="text-sm text-muted-foreground">{resendMessage}</p>
          )}
          <Button
            type="button"
            variant="outline"
            className="w-full"
            disabled={resendLoading}
            onClick={handleResend}
          >
            {resendLoading ? "Sending…" : "Resend verification email"}
          </Button>
          <Link
            href="/login"
            className="inline-flex h-9 w-full items-center justify-center rounded-xl bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 focus-visible:outline focus-visible:ring-2 focus-visible:ring-ring/30"
          >
            Go to Log in
          </Link>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full" style={{ minWidth: "320px", maxWidth: "380px" }}>
      <CardHeader className="space-y-1.5 pb-4">
        <CardTitle>Register</CardTitle>
        <p className="text-sm text-muted-foreground font-normal">
          Create an account to get started
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
              placeholder="Username"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              placeholder="you@example.com"
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
              autoComplete="new-password"
              placeholder="Password"
            />
          </div>
          <Button type="submit" disabled={loading} className="h-9 mt-1">
            {loading ? "Registering…" : "Register"}
          </Button>
          <p className="text-center text-sm text-muted-foreground pt-1">
            Already have an account?{" "}
            <Link href="/login" className="font-medium text-foreground hover:underline">
              Log in
            </Link>
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
