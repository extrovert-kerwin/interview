"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Bot, FileText, User, Waves } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useT } from "@/lib/i18n";

export interface ChatMessage {
  id: string;
  role: "ai" | "user";
  content: string;
  metaKey?: string;
  streaming?: boolean;
  audioUrl?: string;
  audioDurationMs?: number;
  audioMimeType?: string;
}

interface Props {
  messages: ChatMessage[];
  thinking?: boolean;
}

export function ChatStream({ messages, thinking }: Props) {
  const t = useT();
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, thinking]);

  return (
    <div className="flex-1 space-y-5 overflow-y-auto px-1 py-2">
      <AnimatePresence initial={false}>
        {messages.map((m) => (
          <Bubble key={m.id} msg={m} />
        ))}
      </AnimatePresence>
      {thinking && (
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="flex items-start gap-3">
          <Avatar role="ai" />
          <div className="glass inline-flex items-center gap-1.5 rounded-2xl rounded-tl-md px-4 py-3 text-sm text-ink-muted">
            <Dot delay={0} />
            <Dot delay={150} />
            <Dot delay={300} />
            <span className="ml-2 text-xs">{t("chat.thinking")}</span>
          </div>
        </motion.div>
      )}
      <div ref={endRef} />
    </div>
  );
}

function Bubble({ msg }: { msg: ChatMessage }) {
  const t = useT();
  const isAI = msg.role === "ai";
  const [showTranscript, setShowTranscript] = useState(!msg.audioUrl);
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      className={`flex items-start gap-3 ${isAI ? "" : "flex-row-reverse"}`}
    >
      <Avatar role={msg.role} />
      <div
        className={`max-w-[78%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
          isAI
            ? "glass rounded-tl-md text-ink"
            : "rounded-tr-md border border-border bg-gradient-to-br from-violet-500/25 to-cyan-500/15 text-ink"
        }`}
      >
        {msg.metaKey && <div className="mb-1 text-[10px] uppercase tracking-wider text-ink-dim">{t(msg.metaKey)}</div>}

        {msg.audioUrl ? (
          <div className="min-w-[240px] space-y-3">
            <div className="flex items-center gap-2 text-xs text-ink-muted">
              <Waves className="h-4 w-4 text-accent-cyan" />
              <span>{t("chat.voiceAnswer")}</span>
              {msg.audioDurationMs ? <span className="font-mono">{formatDuration(msg.audioDurationMs)}</span> : null}
            </div>
            <audio src={msg.audioUrl} controls className="h-9 w-full max-w-[320px]" />
            <button
              type="button"
              onClick={() => setShowTranscript((v) => !v)}
              className="inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs text-ink-muted transition hover:border-ink/30 hover:text-ink"
            >
              <FileText className="h-3.5 w-3.5" />
              {showTranscript ? t("chat.collapse") : t("chat.toText")}
            </button>
            {showTranscript && <div className="whitespace-pre-wrap rounded-xl border border-border bg-surface px-3 py-2 text-sm leading-relaxed">{msg.content || t("chat.transcribeEmpty")}</div>}
          </div>
        ) : (
          <div className="whitespace-pre-wrap">
            {msg.content}
            {msg.streaming && <span className="ml-0.5 inline-block h-3 w-1 translate-y-0.5 animate-blink bg-accent-violet" />}
          </div>
        )}
      </div>
    </motion.div>
  );
}

function Avatar({ role }: { role: "ai" | "user" }) {
  if (role === "ai") {
    return (
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border bg-surface shadow-glow">
        <Bot className="h-4 w-4 text-accent-violet" />
      </div>
    );
  }
  return (
    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border bg-surface">
      <User className="h-4 w-4 text-accent-cyan" />
    </div>
  );
}

function Dot({ delay }: { delay: number }) {
  return <span className="inline-block h-1.5 w-1.5 animate-blink rounded-full bg-accent-violet" style={{ animationDelay: `${delay}ms` }} />;
}

function formatDuration(ms: number) {
  const total = Math.max(0, Math.round(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = String(total % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}
