"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

/** Legacy route: email verification by code/link is no longer used. */
export default function VerifyEmailPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const next = searchParams.get("next") || "/login";
    router.replace(next);
  }, [router, searchParams]);

  return null;
}
