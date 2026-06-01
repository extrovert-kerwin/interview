"use client";

import { ChevronDown } from "lucide-react";
import { useState } from "react";

import { useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";

interface QAItem {
  q_id: string;
  category: string;
  knowledge_points?: string[];
  question: string;
  answer: string;
  skipped?: boolean;
  follow_ups: { question: string; answer: string; skipped?: boolean }[];
}

interface Evaluation {
  id: string;
  category: string;
  score: number;
  strengths: string;
  gaps: string;
}

interface Props {
  qaHistory: QAItem[];
  evaluations: Evaluation[];
}

function scoreTone(score: number) {
  if (score >= 85) return "text-accent-emerald";
  if (score >= 70) return "text-accent-cyan";
  if (score >= 55) return "text-accent-amber";
  return "text-accent-rose";
}

export function QAReview({ qaHistory, evaluations }: Props) {
  const t = useT();
  const [open, setOpen] = useState<number | null>(0);
  return (
    <div className="glass rounded-2xl p-6">
      <div className="mb-5 flex items-center justify-between">
        <h3 className="text-lg font-medium">{t("qa.title")}</h3>
        <span className="text-xs text-ink-muted">{t("qa.totalFmt", { n: qaHistory.length })}</span>
      </div>
      <div className="space-y-3">
        {qaHistory.map((qa, i) => {
          const ev = evaluations.find((e) => e.id === qa.q_id);
          const score = ev?.score ?? 0;
          const isOpen = open === i;
          const skipped = qa.skipped || qa.answer?.startsWith("[跳过");
          return (
            <div key={qa.q_id} className={cn("rounded-xl border transition", isOpen ? "border-border bg-surface" : "border-border bg-surface/50")}>
              <button onClick={() => setOpen(isOpen ? null : i)} className="flex w-full items-center justify-between gap-4 px-4 py-3 text-left">
                <div className="flex min-w-0 items-center gap-3">
                  <span className="font-mono text-xs text-ink-dim">Q{i + 1}</span>
                  <span className="rounded-full border border-border px-2 py-0.5 text-[10px] uppercase tracking-wider text-ink-muted">{qa.category}</span>
                  {skipped && <span className="rounded-full border border-accent-amber/30 px-2 py-0.5 text-[10px] text-accent-amber">{t("qa.skipped")}</span>}
                  <span className="truncate text-sm text-ink">{qa.question}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className={cn("font-mono text-lg tabular-nums", scoreTone(score))}>{score}</span>
                  <ChevronDown className={cn("h-4 w-4 text-ink-muted transition", isOpen && "rotate-180")} />
                </div>
              </button>
              {isOpen && (
                <div className="space-y-3 border-t border-border px-4 py-4 text-sm">
                  <Block label={t("qa.label.question")} content={qa.question} />
                  {qa.knowledge_points && qa.knowledge_points.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {qa.knowledge_points.map((point) => (
                        <span key={point} className="rounded-full border border-accent-cyan/30 bg-accent-cyan/10 px-2 py-0.5 text-xs text-accent-cyan">
                          {point}
                        </span>
                      ))}
                    </div>
                  )}
                  <Block label={t("qa.label.answer")} content={qa.answer || t("qa.noAnswer")} tone={skipped ? "amber" : undefined} />
                  {qa.follow_ups?.map((f, j) => (
                    <div key={j} className="space-y-1.5">
                      <Block label={t("qa.label.followUp", { n: j + 1 })} content={f.question} accent />
                      <Block label={t("qa.label.answer")} content={f.answer || t("qa.noAnswer")} tone={f.skipped ? "amber" : undefined} />
                    </div>
                  ))}
                  {ev && (
                    <div className="grid gap-3 pt-2 md:grid-cols-2">
                      <Block label={t("qa.label.strengths")} content={ev.strengths || "-"} tone="emerald" />
                      <Block label={t("qa.label.gaps")} content={ev.gaps || "-"} tone="amber" />
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Block({ label, content, tone, accent }: { label: string; content: string; tone?: "emerald" | "amber"; accent?: boolean }) {
  const toneClass =
    tone === "emerald"
      ? "border-accent-emerald/30 bg-accent-emerald/[0.06]"
      : tone === "amber"
        ? "border-accent-amber/30 bg-accent-amber/[0.06]"
        : accent
          ? "border-accent-violet/30 bg-accent-violet/[0.06]"
          : "border-border bg-surface";
  return (
    <div className={cn("rounded-lg border px-3 py-2", toneClass)}>
      <div className="text-[10px] uppercase tracking-wider text-ink-dim">{label}</div>
      <div className="mt-1 whitespace-pre-wrap leading-relaxed text-ink">{content}</div>
    </div>
  );
}
