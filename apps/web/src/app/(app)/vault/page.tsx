"use client";

import type { VaultItem, VaultKind, VaultReveal } from "@nexora/shared-types";
import {
  Check,
  Copy,
  Download,
  Eye,
  EyeOff,
  FileLock2,
  Fingerprint,
  KeyRound,
  Loader2,
  LockKeyhole,
  Plus,
  ShieldCheck,
  StickyNote,
  Trash2,
} from "lucide-react";
import { useEffect, useState } from "react";
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
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useVault, useVaultAudit, useVaultMutations, useVaultStatus } from "@/lib/api/hooks";
import { bytes, formatDateTime, timeAgo } from "@/lib/format";

const KIND_META: Record<VaultKind, { label: string; icon: typeof KeyRound; tone: Tone }> = {
  api_key: { label: "API key", icon: KeyRound, tone: "amber" },
  password: { label: "Password", icon: LockKeyhole, tone: "violet" },
  secret: { label: "Secret", icon: ShieldCheck, tone: "emerald" },
  note: { label: "Secure note", icon: StickyNote, tone: "sky" },
  document: { label: "Document", icon: FileLock2, tone: "pink" },
};

const REVEAL_SECONDS = 30;

function AddItemDialog() {
  const { create } = useVaultMutations();
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<VaultKind>("api_key");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [secret, setSecret] = useState("");
  const [username, setUsername] = useState("");
  const [file, setFile] = useState<File | null>(null);

  async function save() {
    try {
      let file_base64: string | undefined;
      if (kind === "document" && file) {
        if (file.size > 1_500_000) throw new Error("Documents are limited to 1.5 MB");
        const buf = new Uint8Array(await file.arrayBuffer());
        let binary = "";
        buf.forEach((b) => (binary += String.fromCharCode(b)));
        file_base64 = btoa(binary);
      }
      await create.mutateAsync({
        name,
        kind,
        description: description || undefined,
        secret: kind !== "document" ? secret : undefined,
        fields: kind === "password" && username ? { username } : undefined,
        file_base64,
        content_type: file?.type || undefined,
      });
      toast.success("Encrypted and saved");
      setOpen(false);
      setName("");
      setSecret("");
      setUsername("");
      setDescription("");
      setFile(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't save");
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus /> Add item
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add to vault</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Type</Label>
              <Select value={kind} onValueChange={(v) => setKind(v as VaultKind)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(KIND_META).map(([id, m]) => (
                    <SelectItem key={id} value={id}>
                      {m.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="vault-name">Name</Label>
              <Input
                id="vault-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. OpenWeather key"
              />
            </div>
          </div>
          {kind === "password" && (
            <div className="space-y-1.5">
              <Label htmlFor="vault-username">Username (optional)</Label>
              <Input
                id="vault-username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="off"
              />
            </div>
          )}
          {kind === "document" ? (
            <div className="space-y-1.5">
              <Label htmlFor="vault-file">File (max 1.5 MB)</Label>
              <Input id="vault-file" type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </div>
          ) : kind === "note" ? (
            <div className="space-y-1.5">
              <Label htmlFor="vault-secret">Note</Label>
              <Textarea id="vault-secret" rows={5} value={secret} onChange={(e) => setSecret(e.target.value)} />
            </div>
          ) : (
            <div className="space-y-1.5">
              <Label htmlFor="vault-secret">{KIND_META[kind].label}</Label>
              <Input
                id="vault-secret"
                type="password"
                autoComplete="new-password"
                value={secret}
                onChange={(e) => setSecret(e.target.value)}
              />
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="vault-desc">Description (not encrypted, visible in lists)</Label>
            <Input id="vault-desc" value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={save} disabled={create.isPending || !name.trim() || (kind === "document" ? !file : !secret)}>
            {create.isPending && <Loader2 className="animate-spin" />} Encrypt & save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RevealedValue({ data, onHide }: { data: VaultReveal; onHide: () => void }) {
  const [left, setLeft] = useState(REVEAL_SECONDS);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    const t = setInterval(() => setLeft((s) => s - 1), 1000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    if (left <= 0) onHide();
  }, [left, onHide]);

  function download() {
    if (!data.file_base64) return;
    const binary = atob(data.file_base64);
    const arr = Uint8Array.from(binary, (c) => c.charCodeAt(0));
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([arr], { type: data.content_type ?? "application/octet-stream" }));
    a.download = data.name;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  return (
    <div className="border-warning/40 bg-warning/5 mt-3 space-y-2 rounded-xl border p-3 text-sm">
      {data.fields &&
        Object.entries(data.fields).map(([k, v]) => (
          <p key={k}>
            <span className="text-muted-foreground">{k}:</span> <span className="font-mono">{v}</span>
          </p>
        ))}
      {data.secret && (
        <div className="flex items-start gap-2">
          <pre className="min-w-0 flex-1 overflow-x-auto font-mono text-sm break-all whitespace-pre-wrap">
            {data.secret}
          </pre>
          <Button
            size="icon-sm"
            variant="outline"
            aria-label="Copy"
            onClick={async () => {
              await navigator.clipboard.writeText(data.secret ?? "");
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }}
          >
            {copied ? <Check /> : <Copy />}
          </Button>
        </div>
      )}
      {data.file_base64 && (
        <Button size="sm" variant="outline" onClick={download}>
          <Download /> Download file
        </Button>
      )}
      <p className="text-muted-foreground text-xs">Hiding in {left}s · this reveal was recorded in your audit log</p>
    </div>
  );
}

function VaultRow({ item }: { item: VaultItem }) {
  const { reveal, remove } = useVaultMutations();
  const [revealed, setRevealed] = useState<VaultReveal | null>(null);
  const meta = KIND_META[item.kind];

  return (
    <StaggerItem as="li" className="glass hover:border-brand/40 rounded-2xl p-4 transition-colors">
      <div className="flex items-center gap-3">
        <IconTile icon={meta.icon} tone={meta.tone} />
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium">{item.name}</p>
          <p className="text-muted-foreground truncate text-xs">
            {meta.label} · {bytes(item.size_bytes)} ·{" "}
            {item.last_accessed_at ? `opened ${timeAgo(item.last_accessed_at)}` : "never opened"}
            {item.description && ` · ${item.description}`}
          </p>
        </div>
        <Button
          size="sm"
          variant="outline"
          disabled={reveal.isPending}
          onClick={async () => {
            if (revealed) return setRevealed(null);
            try {
              setRevealed(await reveal.mutateAsync(item.id));
            } catch (err) {
              toast.error(err instanceof Error ? err.message : "Couldn't reveal");
            }
          }}
        >
          {reveal.isPending ? <Loader2 className="animate-spin" /> : revealed ? <EyeOff /> : <Eye />}
          {revealed ? "Hide" : "Reveal"}
        </Button>
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button size="icon-sm" variant="ghost" aria-label="Delete">
              <Trash2 />
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete “{item.name}”?</AlertDialogTitle>
              <AlertDialogDescription>The encrypted item is permanently deleted.</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={() => remove.mutate(item.id)}>Delete</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
      {revealed && <RevealedValue data={revealed} onHide={() => setRevealed(null)} />}
    </StaggerItem>
  );
}

export default function VaultPage() {
  const status = useVaultStatus();
  const vault = useVault();
  const audit = useVaultAudit();

  return (
    <div>
      <PageHeader
        tone="emerald"
        title="Secure vault"
        icon={LockKeyhole}
        description="API keys, passwords, notes and documents, encrypted with per-item keys. The assistant can see item names, never their values."
        actions={status.data?.configured ? <AddItemDialog /> : undefined}
      >
        <div className="flex flex-wrap gap-2">
          <HeaderStat icon={KeyRound} label="items" value={<AnimatedNumber value={vault.data?.length ?? 0} />} />
          <HeaderStat icon={ShieldCheck} label="envelope encryption" value="AES-256" />
          <HeaderStat icon={Fingerprint} label="key provider" value={status.data?.key_provider ?? "…"} />
          <HeaderStat icon={Eye} label="reveals audited" value="All" />
        </div>
      </PageHeader>
      {status.data && !status.data.configured && (
        <ErrorState
          className="mb-4"
          error={
            new Error(
              "The vault is not configured on this server. An administrator must set VAULT_MASTER_KEYS or AWS KMS (see docs/security.md).",
            )
          }
        />
      )}
      <Tabs defaultValue="items">
        <TabsList>
          <TabsTrigger value="items">Items</TabsTrigger>
          <TabsTrigger value="audit">Access log</TabsTrigger>
        </TabsList>
        <TabsContent value="items" className="mt-4">
          {vault.isPending ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }, (_, i) => (
                <Skeleton key={i} className="h-16" />
              ))}
            </div>
          ) : vault.error ? (
            <ErrorState error={vault.error} onRetry={() => vault.refetch()} />
          ) : vault.data?.length === 0 ? (
            <EmptyState
              icon={KeyRound}
              title="Your vault is empty"
              description="Store secrets here instead of in chat or memory."
            />
          ) : (
            <Stagger as="ul" className="grid gap-3 md:grid-cols-2">
              {vault.data?.map((item) => (
                <VaultRow key={item.id} item={item} />
              ))}
            </Stagger>
          )}
        </TabsContent>
        <TabsContent value="audit" className="mt-4">
          <div className="overflow-hidden rounded-2xl border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-muted-foreground text-left text-xs">
                <tr>
                  <th className="px-4 py-2">When</th>
                  <th className="px-4 py-2">Action</th>
                  <th className="hidden px-4 py-2 sm:table-cell">Actor</th>
                  <th className="hidden px-4 py-2 md:table-cell">IP</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {audit.data?.items.map((a) => (
                  <tr key={a.id}>
                    <td className="px-4 py-2 whitespace-nowrap">{formatDateTime(a.created_at)}</td>
                    <td className="px-4 py-2 font-mono text-xs">{a.action}</td>
                    <td className="hidden px-4 py-2 capitalize sm:table-cell">{a.actor}</td>
                    <td className="text-muted-foreground hidden px-4 py-2 md:table-cell">{a.ip_address ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {audit.data?.items.length === 0 && (
              <p className="text-muted-foreground p-6 text-center text-sm">No activity yet.</p>
            )}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
