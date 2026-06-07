"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { isAuthenticated } from "@/lib/auth";
import {
  getCurrentUser,
  updateProfile,
  uploadAvatar,
  getAvatarUrl,
  touchAvatarUpdated,
  requestEmailChange,
  confirmEmailChange,
  changePassword,
  type UserProfile,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import Link from "next/link";

export default function ProfilePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [mounted, setMounted] = useState(false);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [profileSaveMsg, setProfileSaveMsg] = useState<string | null>(null);
  const [avatarLoading, setAvatarLoading] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [emailChangeLoading, setEmailChangeLoading] = useState(false);
  const [emailChangeSent, setEmailChangeSent] = useState(false);
  const [confirmEmailMsg, setConfirmEmailMsg] = useState<string | null>(null);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [passwordMsg, setPasswordMsg] = useState<string | null>(null);
  const [avatarKey, setAvatarKey] = useState(0);
  const avatarInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;
    if (!isAuthenticated()) {
      router.replace("/login");
      return;
    }
    getCurrentUser().then((u) => {
      if (u) {
        setUser(u);
        setFirstName(u.first_name ?? "");
        setLastName(u.last_name ?? "");
      }
    });
    const confirmToken = searchParams.get("confirm_email");
    if (confirmToken) {
      confirmEmailChange(confirmToken)
        .then((r) => {
          setConfirmEmailMsg(r.message);
          toast.success(r.message);
          getCurrentUser().then(setUser);
          window.history.replaceState({}, "", "/profile");
        })
        .catch((e) => {
          const msg = e instanceof Error ? e.message : "Failed";
          setConfirmEmailMsg(msg);
          toast.error(msg);
        });
    }
  }, [mounted, router, searchParams]);

  async function handleProfileSave() {
    setProfileSaveMsg(null);
    try {
      await updateProfile({ first_name: firstName.trim() || undefined, last_name: lastName.trim() || undefined });
      setUser((u) => (u ? { ...u, first_name: firstName.trim() || null, last_name: lastName.trim() || null } : null));
      setProfileSaveMsg("Saved");
      toast.success("Profile saved");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed";
      setProfileSaveMsg(msg);
      toast.error(msg);
    }
  }

  function handleAvatarClick() {
    avatarInputRef.current?.click();
  }

  async function handleAvatarChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setAvatarLoading(true);
    try {
      const updated = await uploadAvatar(file);
      setUser(updated);
      setAvatarKey((k) => k + 1);
      touchAvatarUpdated();
      toast.success("Photo updated");
    } catch {
      toast.error("Failed to upload photo");
    } finally {
      setAvatarLoading(false);
      e.target.value = "";
    }
  }

  async function handleRequestEmailChange() {
    if (!newEmail.trim()) return;
    setEmailChangeLoading(true);
    setEmailChangeSent(false);
    try {
      await requestEmailChange(newEmail.trim());
      setEmailChangeSent(true);
      toast.success("Confirmation link sent to your new email");
    } catch (e) {
      setEmailChangeSent(false);
      toast.error(e instanceof Error ? e.message : "Failed to request email change");
    } finally {
      setEmailChangeLoading(false);
    }
  }

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    setPasswordMsg(null);
    setPasswordLoading(true);
    try {
      await changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setPasswordOpen(false);
      setPasswordMsg("Password updated.");
      toast.success("Password updated");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to update password.";
      setPasswordMsg(msg);
      toast.error(msg);
    } finally {
      setPasswordLoading(false);
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
          <h1 className="font-medium text-foreground text-sm">Profile</h1>
        </header>
        <main className="flex-1 p-6 max-w-xl mx-auto w-full">
          <div className="space-y-5">
            {confirmEmailMsg && (
              <p className="text-sm text-green-600 dark:text-green-400 bg-green-500/10 rounded-lg px-3 py-2">
                {confirmEmailMsg}
              </p>
            )}

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Profile</CardTitle>
                <p className="text-sm text-muted-foreground font-normal mt-0.5">
                  Update your name, email, password, and photo
                </p>
              </CardHeader>
              <CardContent className="space-y-4 pt-0">
                <div className="flex items-center gap-4">
                  <button
                    type="button"
                    onClick={handleAvatarClick}
                    disabled={avatarLoading}
                    className="relative shrink-0 size-16 rounded-full overflow-hidden bg-muted flex items-center justify-center text-2xl font-medium text-muted-foreground border-2 border-border"
                  >
                    {user?.avatar_url ? (
                      <img src={getAvatarUrl(user.avatar_url, avatarKey) ?? ""} alt="" className="size-full object-cover" />
                    ) : (
                      (user?.username ?? "?").charAt(0).toUpperCase()
                    )}
                    {avatarLoading && (
                      <span className="absolute inset-0 bg-background/80 flex items-center justify-center text-xs">…</span>
                    )}
                  </button>
                  <input
                    ref={avatarInputRef}
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    className="hidden"
                    onChange={handleAvatarChange}
                  />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-muted-foreground">Photo (JPEG, PNG, WebP, max 3 MB)</p>
                    <Button type="button" variant="outline" size="sm" className="mt-1" onClick={handleAvatarClick} disabled={avatarLoading}>
                      {avatarLoading ? "Uploading…" : "Change photo"}
                    </Button>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <Label htmlFor="first-name">First name</Label>
                    <Input
                      id="first-name"
                      value={firstName}
                      onChange={(e) => setFirstName(e.target.value)}
                      placeholder="First name"
                      className="h-9"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="last-name">Last name</Label>
                    <Input
                      id="last-name"
                      value={lastName}
                      onChange={(e) => setLastName(e.target.value)}
                      placeholder="Last name"
                      className="h-9"
                    />
                  </div>
                </div>
                <Button size="sm" onClick={handleProfileSave}>
                  Save name
                </Button>
                {profileSaveMsg && <p className="text-sm text-muted-foreground">{profileSaveMsg}</p>}

                <div className="space-y-2 pt-2 border-t border-border">
                  <Label>Email</Label>
                  <p className="text-sm text-foreground">{user?.email ?? "—"}</p>
                  <div className="flex flex-wrap gap-2 items-center">
                    <Input
                      type="email"
                      placeholder="New email"
                      value={newEmail}
                      onChange={(e) => setNewEmail(e.target.value)}
                      className="h-9 w-48"
                    />
                    <Button size="sm" onClick={handleRequestEmailChange} disabled={emailChangeLoading}>
                      {emailChangeLoading ? "Sending…" : "Change email"}
                    </Button>
                  </div>
                  {emailChangeSent && (
                    <p className="text-sm text-green-600 dark:text-green-400">
                      We sent a confirmation link to the new address. Check your inbox and click the link.
                    </p>
                  )}
                </div>

                <div className="space-y-3 pt-2 border-t border-border">
                  <Label className="block">Password</Label>
                  {!passwordOpen ? (
                    <Button size="sm" variant="outline" onClick={() => setPasswordOpen(true)}>
                      Change password
                    </Button>
                  ) : (
                    <form onSubmit={handleChangePassword} className="space-y-2 max-w-sm">
                      <Input
                        type="password"
                        placeholder="Current password"
                        value={currentPassword}
                        onChange={(e) => setCurrentPassword(e.target.value)}
                        className="h-9"
                        required
                        autoComplete="current-password"
                      />
                      <Input
                        type="password"
                        placeholder="New password"
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        className="h-9"
                        required
                        minLength={6}
                        autoComplete="new-password"
                      />
                      <div className="flex gap-2">
                        <Button
                          type="submit"
                          size="sm"
                          disabled={passwordLoading || !currentPassword || newPassword.length < 6}
                        >
                          {passwordLoading ? "Updating…" : "Update password"}
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setPasswordOpen(false);
                            setCurrentPassword("");
                            setNewPassword("");
                          }}
                        >
                          Cancel
                        </Button>
                      </div>
                    </form>
                  )}
                  {passwordMsg && <p className="text-sm text-muted-foreground">{passwordMsg}</p>}
                </div>
              </CardContent>
            </Card>
          </div>
        </main>
      </div>
    </div>
  );
}
