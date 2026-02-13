"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSeparator,
  InputOTPSlot,
} from "@/components/ui/input-otp";
import { Label } from "@/components/ui/label";
import { verifyEmail, verifyEmailByCode } from "@/lib/api";

export default function VerifyEmailPage() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [status, setStatus] = useState<"loading" | "success" | "error" | "form">("loading");
  const [message, setMessage] = useState("");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [codeError, setCodeError] = useState("");
  const [codeLoading, setCodeLoading] = useState(false);

  useEffect(() => {
    if (!token) {
      setStatus("form");
      return;
    }
    verifyEmail(token)
      .then((res) => {
        setStatus("success");
        setMessage(res.message);
        toast.success(res.message);
      })
      .catch((err) => {
        setStatus("error");
        const msg = err instanceof Error ? err.message : "Verification failed";
        setMessage(msg);
        toast.error(msg);
      });
  }, [token]);

  async function handleVerifyByCode(e: React.FormEvent) {
    e.preventDefault();
    setCodeError("");
    setCodeLoading(true);
    try {
      await verifyEmailByCode(email, code);
      setStatus("success");
      setMessage("Email verified successfully. You can now log in.");
      toast.success("Email verified successfully. You can now log in.");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Invalid or expired code";
      setCodeError(msg);
      toast.error(msg);
    } finally {
      setCodeLoading(false);
    }
  }

  return (
    <div>
      <Card className="w-full" style={{ minWidth: "320px", maxWidth: "380px" }}>
          <CardHeader className="space-y-1.5 pb-4">
            <CardTitle>
              {status === "loading" && "Verifying…"}
              {status === "success" && "Email verified"}
              {status === "error" && "Verification failed"}
              {status === "form" && "Verify your email"}
            </CardTitle>
            <p className="text-sm text-muted-foreground font-normal">
              {status === "loading" && "Please wait."}
              {status === "success" && message}
              {status === "error" && message}
              {status === "form" && "Enter the email and 6-digit code we sent you."}
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            {status === "form" && (
              <form onSubmit={handleVerifyByCode} className="space-y-3">
                <div className="space-y-2">
                  <Label htmlFor="verify-email">Email</Label>
                  <Input
                    id="verify-email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    placeholder="you@example.com"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Verification code</Label>
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
                </div>
                {codeError && <p className="text-sm text-destructive">{codeError}</p>}
                <Button type="submit" className="w-full" disabled={codeLoading || code.length < 6}>
                  {codeLoading ? "Verifying…" : "Verify"}
                </Button>
              </form>
            )}
            {(status === "success" || status === "error") && (
              <Link
                href="/login"
                className="inline-flex h-9 w-full items-center justify-center rounded-xl bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 focus-visible:outline focus-visible:ring-2 focus-visible:ring-ring/30"
              >
                Go to Log in
              </Link>
            )}
            {status === "form" && (
              <p className="text-center text-sm text-muted-foreground">
                <Link href="/login" className="font-medium text-foreground hover:underline">
                  Back to Log in
                </Link>
              </p>
            )}
          </CardContent>
        </Card>
    </div>
  );
}
