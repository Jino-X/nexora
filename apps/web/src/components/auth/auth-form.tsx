"use client";

import { Info, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth/auth-provider";

type Mode = "login" | "signup" | "forgot";

const COPY: Record<Mode, { title: string; subtitle: string; cta: string }> = {
  login: { title: "Welcome back", subtitle: "Sign in to continue to Nexora.", cta: "Sign in" },
  signup: {
    title: "Create your account",
    subtitle: "Set up your personal assistant in a minute.",
    cta: "Create account",
  },
  forgot: { title: "Reset your password", subtitle: "We'll email you a secure reset link.", cta: "Send reset link" },
};

export function AuthForm({ mode }: { mode: Mode }) {
  const auth = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const copy = COPY[mode];
  const dev = auth.mode === "dev";

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") {
        await auth.signIn(email, password);
        const next = params.get("next");
        router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard");
      } else if (mode === "signup") {
        const { needsConfirmation } = await auth.signUp(email, password, name);
        if (needsConfirmation) setSent(true);
        else router.replace("/onboarding");
      } else {
        await auth.resetPassword(email);
        setSent(true);
        toast.success("Check your inbox for the reset link.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Check your email</h1>
        <p className="text-muted-foreground mt-2 text-sm">
          We sent a link to <span className="text-foreground font-medium">{email}</span>. Open it on this device to
          continue.
        </p>
        <Button asChild variant="outline" className="mt-6 w-full">
          <Link href="/login">Back to sign in</Link>
        </Button>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-3xl font-semibold tracking-tight">{copy.title}</h1>
      <p className="text-muted-foreground mt-1.5 text-sm">{copy.subtitle}</p>

      {dev && (
        <Alert className="mt-5">
          <Info />
          <AlertDescription>
            Development mode: Supabase isn&apos;t configured, so any email signs you in through the API&apos;s dev
            login. Passwords are not checked.
          </AlertDescription>
        </Alert>
      )}

      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        {mode === "signup" && (
          <div className="space-y-1.5">
            <Label htmlFor="name">Name</Label>
            <Input
              id="name"
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Your name"
            />
          </div>
        )}
        <div className="space-y-1.5">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
        </div>
        {mode !== "forgot" && (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="password">Password</Label>
              {mode === "login" && !dev && (
                <Link href="/forgot-password" className="text-muted-foreground hover:text-foreground text-xs">
                  Forgot password?
                </Link>
              )}
            </div>
            <Input
              id="password"
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              required={!dev}
              minLength={dev ? undefined : 8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={dev ? "Not required in dev mode" : "At least 8 characters"}
            />
          </div>
        )}
        {error && (
          <p role="alert" className="text-destructive text-sm">
            {error}
          </p>
        )}
        <Button
          type="submit"
          size="lg"
          className="brand-gradient h-11 w-full rounded-xl text-white shadow-[0_12px_30px_-12px_rgba(124,77,255,0.7)]"
          disabled={busy}
        >
          {busy && <Loader2 className="animate-spin" />}
          {copy.cta}
        </Button>
      </form>

      <p className="text-muted-foreground mt-6 text-center text-sm">
        {mode === "login" ? (
          <>
            New to Nexora?{" "}
            <Link href="/signup" className="text-foreground font-medium hover:underline">
              Create an account
            </Link>
          </>
        ) : (
          <>
            Already have an account?{" "}
            <Link href="/login" className="text-foreground font-medium hover:underline">
              Sign in
            </Link>
          </>
        )}
      </p>
    </div>
  );
}
