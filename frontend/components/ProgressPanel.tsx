"use client";

import { Clock, Target } from "lucide-react";
import { useEffect, useState } from "react";

import { useT } from "@/lib/i18n";

interface Props {
  current: number;
  total: number;
  startedAt: number;
}

export function ProgressPanel({ current, total, startedAt }: Props) {
  const t = useT();
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const displayCurrent = total > 0 ? Math.min(total, current + 1) : current;
  const pct = total > 0 ? Math.min(100, Math.round((displayCurrent / total) * 100)) : 0;
  const seconds = Math.floor((now - startedAt) / 1000);
  const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");
  const loading = total === 0;

  return (
    <div className="space-y-4">
      <div>
        <div className="mb-2 flex items-center justify-between text-xs text-ink-muted">
          <span className="inline-flex items-center gap-1.5">
            <Target className="h-3.5 w-3.5" />
            {t("progress.questions")}
          </span>
          {loading ? (
            <span className="h-3 w-10 animate-pulse rounded bg-surface" />
          ) : (
            <span>{displayCurrent} / {total}</span>
          )}
        </div>
        <div className="progress-track h-1.5 overflow-hidden rounded-full">
          {loading ? (
            <div className="h-full w-1/4 animate-pulse rounded-full bg-accent-violet/30" />
          ) : (
            <div
              className="h-full rounded-full bg-gradient-to-r from-violet-400 to-cyan-400 transition-[width] duration-500"
              style={{ width: `${pct}%` }}
            />
          )}
        </div>
      </div>

      <div className="glass rounded-xl p-3">
        <div className="flex items-center gap-2 text-xs text-ink-muted">
          <Clock className="h-3.5 w-3.5" />
          {t("progress.elapsed")}
        </div>
        <div className="mt-1 font-mono text-2xl tabular-nums">
          {mm}:{ss}
        </div>
      </div>
    </div>
  );
}
