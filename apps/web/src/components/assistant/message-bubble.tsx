"use client";

import type { ApprovalRequest, ResultCard } from "@nexora/shared-types";
import { AlertCircle, Check, Copy, Loader2, RotateCcw, WifiOff, X } from "lucide-react";
import { motion } from "motion/react";
import { memo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { ApprovalCard } from "@/components/assistant/approval-card";
import { ResultCardView } from "@/components/assistant/result-cards";
import { Logo } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatTime, TOOL_LABELS } from "@/lib/format";
import { cn } from "@/lib/utils";

export interface ToolProgress {
  id: string;
  tool: string;
  status: "running" | "ok" | "error";
  message?: string;
}

export interface BubbleProps {
  role: "user" | "assistant";
  content: string;
  createdAt?: string;
  status?: "complete" | "streaming" | "error" | "cancelled";
  tools?: ToolProgress[];
  cards?: ResultCard[];
  approvals?: (ApprovalRequest & { status?: string })[];
  offline?: boolean;
  statusText?: string | null;
  errorText?: string | null;
  channel?: string;
  onRetry?: () => void;
}

const MarkdownBody = memo(function MarkdownBody({ text }: { text: string }) {
  return (
    <div className="prose-nexora">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer noopener">
              {children}
            </a>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
});

export function ToolChips({ tools }: { tools: ToolProgress[] }) {
  if (!tools.length) return null;
  return (
    <div className="mb-2 flex flex-wrap gap-1.5">
      {tools.map((t) => (
        <span
          key={t.id}
          title={t.message}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs",
            t.status === "error" ? "border-destructive/30 text-destructive" : "text-muted-foreground",
          )}
        >
          {t.status === "running" ? (
            <Loader2 className="size-3 animate-spin" />
          ) : t.status === "ok" ? (
            <Check className="text-success size-3" />
          ) : (
            <X className="size-3" />
          )}
          {TOOL_LABELS[t.tool] ?? t.tool}
          {t.status === "error" && t.message && <span className="max-w-48 truncate">: {t.message}</span>}
        </span>
      ))}
    </div>
  );
}

export function MessageBubble(props: BubbleProps) {
  const { role, content, createdAt, status = "complete", tools = [], cards = [], approvals = [], offline } = props;
  const [copied, setCopied] = useState(false);
  const streaming = status === "streaming";

  if (role === "user") {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ type: "spring", stiffness: 320, damping: 28 }}
        className="flex justify-end"
      >
        <div className="max-w-[85%] sm:max-w-[75%]">
          <div className="brand-gradient rounded-3xl rounded-br-lg px-4 py-2.5 text-[0.95rem] whitespace-pre-wrap text-white shadow-[0_10px_30px_-12px_rgba(124,77,255,0.6)]">
            {content}
          </div>
          {createdAt && (
            <p className="text-muted-foreground mt-1 text-right text-[0.7rem]">
              {props.channel === "voice" && "🎙 "}
              {formatTime(createdAt)}
            </p>
          )}
        </div>
      </motion.div>
    );
  }

  async function copy() {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 300, damping: 28 }}
      className="group flex gap-3"
    >
      <span className="relative mt-0.5 grid size-9 shrink-0 place-items-center">
        {streaming && (
          <span
            aria-hidden
            className="animate-orb-spin absolute -inset-1 rounded-2xl bg-[conic-gradient(from_0deg,#8b5cf6,#22d3ee,#f472b6,#8b5cf6)] opacity-80 blur-[2px]"
          />
        )}
        <Logo withText={false} className="relative" />
      </span>
      <div className="glass min-w-0 flex-1 space-y-2 rounded-3xl rounded-tl-lg px-4 py-3">
        <ToolChips tools={tools} />
        {props.statusText && streaming && !content && tools.length === 0 && (
          <p className="text-muted-foreground text-sm">{props.statusText}</p>
        )}
        {(content || (streaming && tools.length === 0 && !props.statusText)) && (
          <div className={cn(status === "error" && "text-muted-foreground")}>
            {content ? <MarkdownBody text={content} /> : null}
            {streaming && (
              <span className="animate-caret bg-foreground/70 ml-0.5 inline-block h-4 w-1.5 align-text-bottom" />
            )}
          </div>
        )}
        {cards.length > 0 && (
          <div className="grid gap-3">
            {cards.map((card, i) => (
              <ResultCardView key={i} card={card} />
            ))}
          </div>
        )}
        {approvals.map((a) => (
          <ApprovalCard
            key={a.approval_id}
            approvalId={a.approval_id}
            tool={a.tool}
            summary={a.summary}
            initialStatus={a.status ?? "pending"}
          />
        ))}
        {(status === "error" || status === "cancelled" || props.errorText) && (
          <p className="text-destructive inline-flex items-center gap-1.5 text-sm">
            <AlertCircle className="size-4" />
            {props.errorText ?? (status === "cancelled" ? "Stopped" : "This response failed")}
          </p>
        )}
        {!streaming && (
          <div className="text-muted-foreground flex items-center gap-1 text-[0.7rem]">
            {createdAt && <span className="mr-1">{formatTime(createdAt)}</span>}
            {offline && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5">
                    <WifiOff className="size-3" /> Offline mode
                  </span>
                </TooltipTrigger>
                <TooltipContent>
                  No language model was reachable; this reply was assembled from tool results.
                </TooltipContent>
              </Tooltip>
            )}
            <span className="flex gap-0.5 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100">
              {content && (
                <Button size="icon-xs" variant="ghost" onClick={copy} aria-label="Copy response">
                  {copied ? <Check /> : <Copy />}
                </Button>
              )}
              {props.onRetry && (
                <Button size="icon-xs" variant="ghost" onClick={props.onRetry} aria-label="Retry">
                  <RotateCcw />
                </Button>
              )}
            </span>
          </div>
        )}
      </div>
    </motion.div>
  );
}
