"use client";

import { ArrowLeft, ArrowRight, Brain, Check, Languages, Loader2, MapPin, Newspaper } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { IconTile, Logo, type Tone } from "@/components/common";
import { AuroraBackground } from "@/components/fx/aurora-background";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useGeolocation } from "@/hooks/use-geolocation";
import { useMe, useOnboarding } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

const LANGS = [
  { id: "auto", label: "Automatic", hint: "Reply in the language I use" },
  { id: "en", label: "English", hint: "Always reply in English" },
  { id: "ta", label: "தமிழ் Tamil", hint: "Reply in Tamil" },
] as const;

const CATEGORIES = ["world", "india", "technology", "ai", "business", "science"];

export default function OnboardingPage() {
  const router = useRouter();
  const me = useMe();
  const onboard = useOnboarding();
  const geo = useGeolocation();
  const [step, setStep] = useState(0);
  const [nameDraft, setName] = useState<string | null>(null);
  const [language, setLanguage] = useState<"auto" | "en" | "ta">("auto");
  const [categories, setCategories] = useState<string[]>(["world", "technology", "ai"]);
  const [memory, setMemory] = useState(true);
  const timezone = useMemo(() => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC", []);

  const name = nameDraft ?? me.data?.profile.display_name ?? "";

  async function finish() {
    try {
      await onboard.mutateAsync({
        display_name: name.trim() || "Friend",
        timezone,
        preferred_language: language,
        news_categories: categories,
        memory_enabled: memory,
        home_latitude: geo.coords?.latitude ?? null,
        home_longitude: geo.coords?.longitude ?? null,
        home_label: geo.coords ? "Home" : null,
      });
      router.replace("/dashboard");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't save your setup");
    }
  }

  const steps = [
    {
      icon: Languages,
      title: "Let's get to know you",
      body: (
        <div className="space-y-5">
          <div className="space-y-1.5">
            <Label htmlFor="name">What should Nexora call you?</Label>
            <Input id="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" autoFocus />
          </div>
          <div className="space-y-2">
            <Label>Preferred language</Label>
            <div className="grid gap-2">
              {LANGS.map((l) => (
                <button
                  key={l.id}
                  type="button"
                  onClick={() => setLanguage(l.id)}
                  className={cn(
                    "flex items-center justify-between rounded-xl border px-4 py-3 text-left transition-colors",
                    language === l.id ? "border-brand bg-brand-soft" : "hover:bg-muted",
                  )}
                >
                  <span>
                    <span className="block font-medium">{l.label}</span>
                    <span className="text-muted-foreground text-xs">{l.hint}</span>
                  </span>
                  {language === l.id && <Check className="text-brand size-4" />}
                </button>
              ))}
            </div>
          </div>
          <p className="text-muted-foreground text-xs">Timezone detected: {timezone}</p>
        </div>
      ),
    },
    {
      icon: MapPin,
      title: "Local weather and places",
      body: (
        <div className="space-y-4 text-sm">
          <p className="text-muted-foreground">
            Share your approximate location once to set a home location for weather and your morning briefing. You can
            change or clear it any time in Settings. Nexora only asks your browser for location when you allow it.
          </p>
          <Button variant="outline" onClick={geo.request} disabled={geo.status === "locating"}>
            {geo.status === "locating" ? <Loader2 className="animate-spin" /> : <MapPin />}
            {geo.coords ? "Location set" : "Use my current location"}
          </Button>
          {geo.coords && (
            <p className="text-success">
              <Check className="mr-1 inline size-4" /> Home set to {geo.coords.latitude.toFixed(3)},{" "}
              {geo.coords.longitude.toFixed(3)}
            </p>
          )}
          {geo.error && <p className="text-destructive">{geo.error}</p>}
        </div>
      ),
    },
    {
      icon: Newspaper,
      title: "What news do you follow?",
      body: (
        <div className="flex flex-wrap gap-2">
          {CATEGORIES.map((c) => {
            const on = categories.includes(c);
            return (
              <button
                key={c}
                type="button"
                onClick={() => setCategories(on ? categories.filter((x) => x !== c) : [...categories, c])}
                className={cn(
                  "rounded-full border px-4 py-1.5 text-sm capitalize transition-colors",
                  on ? "border-brand bg-brand text-brand-foreground" : "hover:bg-muted",
                )}
              >
                {c === "ai" ? "AI" : c}
              </button>
            );
          })}
        </div>
      ),
    },
    {
      icon: Brain,
      title: "Personal memory",
      body: (
        <div className="space-y-4 text-sm">
          <p className="text-muted-foreground">
            When you ask, Nexora remembers facts (&quot;remember that my sister lives in Coimbatore&quot;) to give
            better answers. You can see, edit, export or delete every memory. Passwords and keys belong in the encrypted
            vault and are never stored as memories.
          </p>
          <label className="flex items-center justify-between rounded-xl border px-4 py-3">
            <span className="font-medium">Enable personal memory</span>
            <Switch checked={memory} onCheckedChange={setMemory} />
          </label>
        </div>
      ),
    },
  ];

  const current = steps[step];
  const TONES_BY_STEP: Tone[] = ["violet", "cyan", "amber", "rose"];

  return (
    <div className="relative flex min-h-dvh items-center justify-center px-5 py-10">
      <AuroraBackground />
      <div className="glass-strong gradient-border w-full max-w-lg rounded-[2rem] p-7 sm:p-9">
        <div className="mb-8 flex items-center justify-between">
          <Logo />
          <span className="text-muted-foreground text-xs font-medium">
            Step {step + 1} of {steps.length}
          </span>
        </div>
        <div className="mb-7 flex gap-1.5">
          {steps.map((_, i) => (
            <span key={i} className="bg-muted relative h-1.5 flex-1 overflow-hidden rounded-full">
              <motion.span
                className="brand-gradient absolute inset-y-0 left-0 rounded-full"
                initial={false}
                animate={{ width: i <= step ? "100%" : "0%" }}
                transition={{ type: "spring", stiffness: 200, damping: 26 }}
              />
            </span>
          ))}
        </div>
        <AnimatePresence mode="wait">
          <motion.div
            key={step}
            initial={{ opacity: 0, x: 24 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -24 }}
            transition={{ type: "spring", stiffness: 260, damping: 28 }}
          >
            <IconTile icon={current.icon} tone={TONES_BY_STEP[step]} size="lg" className="animate-float mb-5" />
            <h1 className="mb-5 text-3xl font-semibold tracking-tight">{current.title}</h1>
            {current.body}
          </motion.div>
        </AnimatePresence>
        <div className="mt-9 flex justify-between">
          <Button variant="ghost" onClick={() => setStep(step - 1)} disabled={step === 0}>
            <ArrowLeft /> Back
          </Button>
          {step < steps.length - 1 ? (
            <Button className="brand-gradient rounded-xl px-5 text-white" onClick={() => setStep(step + 1)}>
              Continue <ArrowRight />
            </Button>
          ) : (
            <Button className="brand-gradient rounded-xl px-5 text-white" onClick={finish} disabled={onboard.isPending}>
              {onboard.isPending && <Loader2 className="animate-spin" />} Finish setup
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
