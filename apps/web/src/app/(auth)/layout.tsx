import { Brain, Languages, ShieldCheck } from "lucide-react";
import Link from "next/link";

import { Logo } from "@/components/common";
import { AuroraBackground } from "@/components/fx/aurora-background";
import { Orb3D } from "@/components/fx/orb-3d";

const FEATURES = [
  {
    icon: Languages,
    title: "Tamil & English",
    text: "Talk naturally, mix languages freely",
    pos: "top-[14%] left-[6%]",
    delay: "0s",
  },
  {
    icon: Brain,
    title: "Remembers you",
    text: "Your memory, fully in your control",
    pos: "top-[46%] right-[4%]",
    delay: "1.2s",
  },
  {
    icon: ShieldCheck,
    title: "You approve first",
    text: "Nothing is sent without your OK",
    pos: "bottom-[12%] left-[12%]",
    delay: "2.4s",
  },
];

export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="relative grid min-h-dvh lg:grid-cols-[1.15fr_1fr]">
      <AuroraBackground />
      <aside className="relative hidden flex-col justify-between overflow-hidden p-10 lg:flex">
        <Link href="/" className="relative z-10">
          <Logo />
        </Link>
        <div className="relative mx-auto w-full max-w-xl">
          <Orb3D mood="listening" className="mx-auto w-[min(30rem,80%)]" />
          {FEATURES.map((f) => (
            <div
              key={f.title}
              className={`glass animate-float absolute ${f.pos} flex items-center gap-3 rounded-2xl px-4 py-3 shadow-xl`}
              style={{ animationDelay: f.delay }}
            >
              <span className="brand-gradient grid size-9 place-items-center rounded-xl text-white">
                <f.icon className="size-4" />
              </span>
              <span>
                <span className="block text-sm font-semibold">{f.title}</span>
                <span className="text-muted-foreground block text-xs">{f.text}</span>
              </span>
            </div>
          ))}
        </div>
        <div className="relative z-10 max-w-lg">
          <p className="font-heading text-3xl leading-tight font-semibold tracking-tight">
            “Hey Nexora, <span className="text-shimmer">what does my day look like?</span>”
          </p>
          <p className="text-muted-foreground mt-3">
            Your personal assistant for weather, news, places, email, reminders and more, by text or voice.
          </p>
        </div>
      </aside>
      <main className="relative flex items-center justify-center px-5 py-10">
        <div className="glass-strong gradient-border w-full max-w-md rounded-[2rem] p-7 sm:p-9">
          <div className="mb-8 lg:hidden">
            <Logo />
          </div>
          {children}
        </div>
      </main>
    </div>
  );
}
