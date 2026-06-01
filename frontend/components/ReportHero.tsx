"use client";

import { motion } from "framer-motion";

import { useT } from "@/lib/i18n";

const RECOMMEND_COLORS: Record<string, string> = {
  强烈推荐: "from-emerald-400 to-cyan-400 text-emerald-300 border-emerald-400/40",
  推荐: "from-cyan-400 to-violet-400 text-cyan-300 border-cyan-400/40",
  待定: "from-amber-400 to-rose-400 text-amber-300 border-amber-400/40",
  不推荐: "from-rose-500 to-rose-400 text-rose-300 border-rose-400/40",
};

interface Props {
  score: number;
  recommendation: string;
  summary: string;
  candidate?: string;
  position?: string;
  completion?: {
    answered: number;
    skipped: number;
    total_seen: number;
    target_total?: number;
    follow_ups: number;
    completion_rate?: number;
  };
}

export function ReportHero({ score, recommendation, summary, candidate, position, completion }: Props) {
  const t = useT();
  const colorClass = RECOMMEND_COLORS[recommendation] || RECOMMEND_COLORS["推荐"];
  const completionRate = completion?.completion_rate != null ? Math.round(completion.completion_rate * 100) : null;
  return (
    <div className="glass relative overflow-hidden rounded-2xl p-8 md:p-10">
      <div className="absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-white/30 to-transparent" />
      <div className="relative grid items-center gap-8 md:grid-cols-[auto,1fr]">
        <ScoreRing score={score} />
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <span
              className={`inline-flex rounded-full border bg-gradient-to-r bg-clip-text px-3 py-1 text-sm font-medium ${colorClass}`}
              style={{ WebkitTextFillColor: "transparent" }}
            >
              {recommendation}
            </span>
            {candidate && <span className="text-sm text-ink-muted">{t("hero.candidate")}{candidate}</span>}
            {position && <span className="text-sm text-ink-muted">{t("hero.position")}{position}</span>}
          </div>
          <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">{t("hero.heading")}</h1>
          <p className="max-w-3xl text-base leading-relaxed text-ink">{summary}</p>
          {completion && (
            <div className="grid max-w-2xl grid-cols-2 gap-2 text-xs sm:grid-cols-5">
              <Metric label={t("hero.metric.answered")} value={completion.answered} />
              <Metric label={t("hero.metric.skipped")} value={completion.skipped} />
              <Metric label={t("hero.metric.totalSeen")} value={completion.total_seen} />
              <Metric label={t("hero.metric.followUps")} value={completion.follow_ups} />
              <Metric label={t("hero.metric.completion")} value={completionRate != null ? `${completionRate}%` : "-"} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-2">
      <div className="text-ink-dim">{label}</div>
      <div className="mt-1 font-mono text-lg text-ink">{value}</div>
    </div>
  );
}

function ScoreRing({ score }: { score: number }) {
  const size = 160;
  const stroke = 12;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const offset = c - (score / 100) * c;

  return (
    <motion.div
      initial={{ scale: 0.92, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ duration: 0.6, ease: "easeOut" }}
      className="relative flex items-center justify-center"
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} className="-rotate-90">
        <defs>
          <linearGradient id="ringGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#a78bfa" />
            <stop offset="100%" stopColor="#22d3ee" />
          </linearGradient>
        </defs>
        <circle cx={size / 2} cy={size / 2} r={r} stroke="rgba(128,128,128,0.18)" strokeWidth={stroke} fill="none" />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke="url(#ringGrad)"
          strokeWidth={stroke}
          strokeLinecap="round"
          fill="none"
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 1.2, ease: "easeOut" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="font-mono text-5xl font-semibold tabular-nums">{score}</div>
        <div className="text-xs uppercase tracking-wider text-ink-dim">/ 100</div>
      </div>
    </motion.div>
  );
}
