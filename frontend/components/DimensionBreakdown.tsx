"use client";

import { BarChart3 } from "lucide-react";

import type { DimensionDetail } from "@/lib/api";
import { useT } from "@/lib/i18n";

interface Props {
  details?: DimensionDetail[];
}

export function DimensionBreakdown({ details }: Props) {
  const t = useT();
  if (!details?.length) return null;
  return (
    <section className="glass rounded-2xl p-6">
      <div className="mb-5 flex items-center gap-2">
        <BarChart3 className="h-4 w-4 text-accent-cyan" />
        <h2 className="text-base font-medium">{t("dimBreak.title")}</h2>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {details.map((item) => (
          <article key={item.name} className="rounded-2xl border border-border bg-surface p-4">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <h3 className="font-medium text-ink">{item.name}</h3>
                <p className="mt-1 text-xs text-ink-dim">
                  {t("dimBreak.row", { level: item.level, evidence: item.evidence_count, skipped: item.skipped_count })}
                </p>
              </div>
              <span className="font-mono text-2xl text-ink">{item.score}</span>
            </div>
            <div className="progress-track h-2 overflow-hidden rounded-full">
              <div
                className="h-full rounded-full bg-gradient-to-r from-accent-violet via-accent-cyan to-accent-emerald"
                style={{ width: `${Math.max(4, Math.min(100, item.score))}%` }}
              />
            </div>
            <p className="mt-3 text-sm leading-relaxed text-ink-muted">{item.insight}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
