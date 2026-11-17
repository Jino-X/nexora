"use client";

import type { Memory, MemoryKind } from "@nexora/shared-types";
import {
  Brain,
  Download,
  FolderKanban,
  Heart,
  Lightbulb,
  Loader2,
  MessagesSquare,
  Pencil,
  Pin,
  PinOff,
  Plus,
  Search,
  Settings2,
  Sparkles,
  StickyNote,
  Trash2,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useDeferredValue, useState } from "react";
import { toast } from "sonner";

import { EmptyState, ErrorState, HeaderStat, IconTile, PageHeader, type Tone } from "@/components/common";
import { AnimatedNumber, Stagger, StaggerItem } from "@/components/fx/motion";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api/client";
import { useMe, useMemories, useMemoryMutations, useUpdatePreferences } from "@/lib/api/hooks";
import { timeAgo } from "@/lib/format";

const KIND_ICONS: Record<string, LucideIcon> = {
  fact: Lightbulb,
  preference: Heart,
  project: FolderKanban,
  profile: UserRound,
  note: StickyNote,
  conversation_summary: MessagesSquare,
};

const KIND_TONES: Record<string, Tone> = {
  fact: "violet",
  preference: "pink",
  project: "amber",
  profile: "sky",
  note: "emerald",
  conversation_summary: "cyan",
};

const KINDS: { id: MemoryKind; label: string }[] = [
  { id: "fact", label: "Fact" },
  { id: "preference", label: "Preference" },
  { id: "project", label: "Project" },
  { id: "profile", label: "Profile" },
  { id: "note", label: "Note" },
  { id: "conversation_summary", label: "Summary" },
];

function MemoryEditor({
  open,
  onOpenChange,
  memory,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  memory: Memory | null;
}) {
  const { create, update } = useMemoryMutations();
  const [content, setContent] = useState(memory?.content ?? "");
  const [kind, setKind] = useState<MemoryKind>(memory?.kind ?? "fact");
  const busy = create.isPending || update.isPending;

  async function save() {
    try {
      if (memory) await update.mutateAsync({ id: memory.id, content, kind });
      else await create.mutateAsync({ content, kind });
      toast.success(memory ? "Memory updated" : "Memory saved");
      onOpenChange(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't save");
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{memory ? "Edit memory" : "Add a memory"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="memory-content">What should Nexora remember?</Label>
            <Textarea
              id="memory-content"
              rows={4}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="e.g. My upcoming project is a Tamil voice assistant launching in December."
            />
            <p className="text-muted-foreground text-xs">
              Passwords and keys are refused here. Use the vault for those.
            </p>
          </div>
          <div className="space-y-1.5">
            <Label>Type</Label>
            <Select value={kind} onValueChange={(v) => setKind(v as MemoryKind)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {KINDS.map((k) => (
                  <SelectItem key={k.id} value={k.id}>
                    {k.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={save} disabled={busy || !content.trim()}>
            {busy && <Loader2 className="animate-spin" />} Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function MemoryPage() {
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("all");
  const deferred = useDeferredValue(query);
  const memories = useMemories(deferred, kind === "all" ? "" : kind);
  const { update, remove, removeAll } = useMemoryMutations();
  const me = useMe();
  const updatePrefs = useUpdatePreferences();
  const [editing, setEditing] = useState<Memory | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const prefs = me.data?.preferences;

  async function exportAll() {
    const data = await api<unknown>("/memories/export");
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `nexora-memories-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  return (
    <div>
      <PageHeader
        tone="rose"
        title="Memory"
        icon={Brain}
        description="What Nexora remembers about you. It only saves things you ask it to remember. Everything here is yours to edit or delete."
        actions={
          <>
            <Button variant="outline" onClick={exportAll}>
              <Download /> Export
            </Button>
            <Button
              className="brand-gradient text-white"
              onClick={() => {
                setEditing(null);
                setEditorOpen(true);
              }}
            >
              <Plus /> Add memory
            </Button>
          </>
        }
      >
        <div className="flex flex-wrap gap-2">
          <HeaderStat
            icon={Brain}
            label="memories"
            value={<AnimatedNumber value={memories.data?.items.length ?? 0} />}
          />
          <HeaderStat
            icon={Pin}
            label="pinned"
            value={<AnimatedNumber value={memories.data?.items.filter((x) => x.pinned).length ?? 0} />}
          />
          <HeaderStat icon={Sparkles} label="memory" value={prefs?.memory_enabled === false ? "Off" : "On"} />
        </div>
      </PageHeader>

      <div className="glass mb-5 grid gap-3 rounded-2xl p-4 sm:grid-cols-2">
        <label className="flex items-center justify-between gap-4">
          <span>
            <span className="block text-sm font-medium">Use personal memory</span>
            <span className="text-muted-foreground text-xs">When off, Nexora neither reads nor saves memories.</span>
          </span>
          <Switch
            checked={prefs?.memory_enabled ?? true}
            onCheckedChange={(v) => updatePrefs.mutate({ memory_enabled: v })}
            disabled={!prefs}
          />
        </label>
        <div className="flex items-center justify-between gap-4">
          <span>
            <span className="block text-sm font-medium">Retention</span>
            <span className="text-muted-foreground text-xs">
              {prefs?.memory_retention_days
                ? `New memories expire after ${prefs.memory_retention_days} days`
                : "Kept until you delete them"}
            </span>
          </span>
          <Button asChild size="sm" variant="ghost">
            <Link href="/settings?tab=privacy">
              <Settings2 /> Privacy
            </Link>
          </Button>
        </div>
      </div>

      <div className="mb-4 flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1">
          <Search className="text-muted-foreground absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search memories by meaning…"
            className="pl-8"
          />
        </div>
        <Select value={kind} onValueChange={setKind}>
          <SelectTrigger className="sm:w-44" aria-label="Filter by type">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All types</SelectItem>
            {KINDS.map((k) => (
              <SelectItem key={k.id} value={k.id}>
                {k.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {memories.isPending ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      ) : memories.error ? (
        <ErrorState error={memories.error} onRetry={() => memories.refetch()} />
      ) : memories.data?.items.length === 0 ? (
        <EmptyState
          icon={Brain}
          tone="rose"
          title={query ? "No matching memories" : "Nothing remembered yet"}
          description="Say “Remember that…” in chat, or add one here."
        />
      ) : (
        <Stagger as="ul" className="grid gap-3 md:grid-cols-2">
          {memories.data?.items.map((m) => (
            <StaggerItem
              as="li"
              key={m.id}
              className="group glass hover:border-brand/40 flex items-start gap-3 rounded-2xl p-4 transition-colors"
            >
              <IconTile icon={KIND_ICONS[m.kind] ?? Lightbulb} tone={KIND_TONES[m.kind] ?? "violet"} size="md" />
              <div className="min-w-0 flex-1">
                <p className="text-[0.95rem]">{m.content}</p>
                <div className="text-muted-foreground mt-2 flex flex-wrap items-center gap-1.5 text-xs">
                  <Badge variant="secondary" className="capitalize">
                    {m.kind.replace("_", " ")}
                  </Badge>
                  <span>
                    saved {timeAgo(m.created_at)} by {m.source}
                  </span>
                  {m.last_used_at && <span>· used {timeAgo(m.last_used_at)}</span>}
                  {m.expires_at && <span>· expires {timeAgo(m.expires_at)}</span>}
                  {m.score !== null && m.score > 0 && <span>· match {(m.score * 100).toFixed(0)}%</span>}
                </div>
              </div>
              <div className="flex shrink-0 gap-0.5">
                <Button
                  size="icon-sm"
                  variant="ghost"
                  aria-label={m.pinned ? "Unpin" : "Pin"}
                  onClick={() => update.mutate({ id: m.id, pinned: !m.pinned })}
                >
                  {m.pinned ? <PinOff /> : <Pin />}
                </Button>
                <Button
                  size="icon-sm"
                  variant="ghost"
                  aria-label="Edit"
                  onClick={() => {
                    setEditing(m);
                    setEditorOpen(true);
                  }}
                >
                  <Pencil />
                </Button>
                <Button
                  size="icon-sm"
                  variant="ghost"
                  aria-label="Delete"
                  onClick={() => remove.mutate(m.id, { onSuccess: () => toast.success("Forgotten") })}
                >
                  <Trash2 />
                </Button>
              </div>
            </StaggerItem>
          ))}
        </Stagger>
      )}

      {Boolean(memories.data?.items.length) && (
        <div className="mt-8 flex justify-end">
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive" size="sm">
                <Trash2 /> Delete all memories
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete every memory?</AlertDialogTitle>
                <AlertDialogDescription>
                  This permanently removes everything Nexora remembers about you. It can&apos;t be undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={() =>
                    removeAll.mutate(undefined, { onSuccess: () => toast.success("All memories deleted") })
                  }
                >
                  Delete all
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      )}

      {editorOpen && (
        <MemoryEditor key={editing?.id ?? "new"} open={editorOpen} onOpenChange={setEditorOpen} memory={editing} />
      )}
    </div>
  );
}
