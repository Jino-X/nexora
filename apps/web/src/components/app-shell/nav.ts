import type { Tone } from "@/components/common";
import {
  Bell,
  Brain,
  Compass,
  History,
  KeyRound,
  LayoutDashboard,
  ListChecks,
  MessageSquare,
  Plug,
  Settings,
  Workflow,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  group: "main" | "personal" | "activity" | "system";
  tone: Tone;
}

export const NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, group: "main", tone: "violet" },
  { href: "/assistant", label: "Assistant", icon: MessageSquare, group: "main", tone: "pink" },
  { href: "/discover", label: "Discover", icon: Compass, group: "main", tone: "cyan" },
  { href: "/memory", label: "Memory", icon: Brain, group: "personal", tone: "rose" },
  { href: "/vault", label: "Vault", icon: KeyRound, group: "personal", tone: "emerald" },
  { href: "/automations", label: "Automations", icon: Workflow, group: "personal", tone: "amber" },
  { href: "/tasks", label: "Tasks", icon: ListChecks, group: "activity", tone: "sky" },
  { href: "/history", label: "History", icon: History, group: "activity", tone: "violet" },
  { href: "/notifications", label: "Notifications", icon: Bell, group: "activity", tone: "rose" },
  { href: "/integrations", label: "Integrations", icon: Plug, group: "system", tone: "lime" },
  { href: "/settings", label: "Settings", icon: Settings, group: "system", tone: "sky" },
];

export const GROUP_LABELS: Record<NavItem["group"], string> = {
  main: "",
  personal: "Personal",
  activity: "Activity",
  system: "Setup",
};
