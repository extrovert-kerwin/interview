"use client";

import { motion } from "framer-motion";
import { Activity } from "lucide-react";
import { useMemo, useState } from "react";

import { FinalReport } from "@/lib/api";

type Per = FinalReport["per_question"][number] & {
  rubric_scores?: Record<string, { label?: string; score?: number; weight?: number }>;
  evidence_quality?: number;
  uncertainty?: number;
};

interface Props {
  perQuestion: Per[];
}

function cellColor(score?: number) {
  if (score == null) return "rgba(148,163,184,0.15)";
  if (score >= 80) return "rgba(52,211,153,0.85)";
  if (score >= 65) return "rgba(34,211,238,0.85)";
  if (score >= 50) return "rgba(251,191,36,0.85)";
  if (score >= 30) return "rgba(251,113,133,0.85)";
  return "rgba(244,63,94,0.85)";
}

export function QuestionRubricGrid({ perQuestion }: Props) {
  const [hover, setHover] = useState<{ q: number; d: number } | null>(null);

  const { questions, dimensions } = useMemo(() => {
    const dimMap = new Map<string, string>();
    perQuestion.forEach((q) => {
      const rubric = q.rubric_scores || {};
      Object.entries(rubric).forEach(([key, v]) => {
        if (!dimMap.has(key)) dimMap.set(key, v?.label || key);
      });
    });
    const dimensions = Array.from(dimMap.entries()).map(([key, label]) => ({ key, label }));
    return { questions: perQuestion, dimensions };
  }, [perQuestion]);

  if (!questions.length || !dimensions.length) return null;

  const hoveredQ = hover ? questions[hover.q] : null;
  const hoveredDim = hover ? dimensions[hover.d] : null;
  const hoveredScore = hover
    ? hoveredQ?.rubric_scores?.[hoveredDim!.key]?.score
    : null;

  return (
    <section className="glass-strong relative overflow-hidden rounded-2xl p-6">
      <div className="noise-layer rounded-2xl" />
      <div className="relative mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-accent-cyan" />
            <h2 className="text-base font-medium">逐题表现热力图</h2>
          </div>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-ink-muted">
            横轴是每道题，纵轴是评分维度。颜色越绿表示这题这一维度做得越扎实，越红越是失分点。把鼠标停在格子上能看到具体打分。
          </p>
        </div>
        <ScaleLegend />
      </div>

      <div className="relative overflow-x-auto pb-2">
        <div className="relative" style={{ minWidth: `${Math.max(420, questions.length * 56 + 130)}px` }}>
          <div
            className="grid gap-1.5"
            style={{
              gridTemplateColumns: `130px repeat(${questions.length}, minmax(44px, 1fr)) 60px`,
            }}
          >
            <div />
            {questions.map((q, qi) => (
              <div key={`h-${qi}`} className="text-center">
                <div className="font-mono text-[10px] text-ink-dim">Q{qi + 1}</div>
                <div className="mx-auto mt-0.5 inline-block max-w-[60px] truncate rounded-full bg-surface px-1.5 py-0.5 text-[10px] text-ink-muted" title={q.category}>
                  {q.category}
                </div>
              </div>
            ))}
            <div className="text-center font-mono text-[10px] text-ink-dim">总分</div>

            {dimensions.map((dim, di) => (
              <DimensionRow
                key={dim.key}
                label={dim.label}
                cells={questions.map((q) => q.rubric_scores?.[dim.key]?.score)}
                weight={questions[0]?.rubric_scores?.[dim.key]?.weight}
                onCellEnter={(qi) => setHover({ q: qi, d: di })}
                onLeave={() => setHover(null)}
              />
            ))}

            <div className="pt-2 text-xs font-medium text-ink-muted">综合</div>
            {questions.map((q, qi) => (
              <div key={`tot-${qi}`} className="pt-2">
                <Cell score={q.score} large />
              </div>
            ))}
            <div className="pt-2" />
          </div>
        </div>

        {hover && hoveredQ && hoveredDim && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            className="pointer-events-none absolute right-2 top-2 rounded-2xl border border-border bg-background/90 px-3 py-2 shadow-glow-soft backdrop-blur-xl"
          >
            <div className="text-[10px] text-ink-dim">
              Q{hover.q + 1} · {hoveredQ.category}
            </div>
            <div className="mt-1 flex items-center gap-2 text-sm font-medium text-ink">
              {hoveredDim.label}
              <span className="font-mono" style={{ color: cellColor(hoveredScore ?? undefined) }}>
                {hoveredScore ?? "--"}
              </span>
            </div>
          </motion.div>
        )}
      </div>
    </section>
  );
}

function DimensionRow({
  label,
  cells,
  weight,
  onCellEnter,
  onLeave,
}: {
  label: string;
  cells: (number | undefined)[];
  weight?: number;
  onCellEnter: (qi: number) => void;
  onLeave: () => void;
}) {
  const avg = useMemo(() => {
    const valid = cells.filter((c): c is number => typeof c === "number");
    if (!valid.length) return null;
    return Math.round(valid.reduce((s, n) => s + n, 0) / valid.length);
  }, [cells]);
  return (
    <>
      <div className="flex items-center justify-between gap-2 pr-2">
        <span className="text-xs text-ink-muted">{label}</span>
        {weight != null && (
          <span className="font-mono text-[10px] text-ink-dim">{Math.round(weight * 100)}%</span>
        )}
      </div>
      {cells.map((score, qi) => (
        <button
          key={qi}
          type="button"
          onMouseEnter={() => onCellEnter(qi)}
          onMouseLeave={onLeave}
          onFocus={() => onCellEnter(qi)}
          className="tap-shrink rounded-md transition focus:outline-none focus:ring-1 focus:ring-accent-cyan/60"
        >
          <Cell score={score} />
        </button>
      ))}
      <div className="text-right">
        <span className="font-mono text-xs text-ink">{avg ?? "--"}</span>
      </div>
    </>
  );
}

function Cell({ score, large = false }: { score?: number; large?: boolean }) {
  const color = cellColor(score);
  return (
    <div
      className={`rounded-md ${large ? "h-9" : "h-7"} flex items-center justify-center`}
      style={{
        backgroundColor: color,
        boxShadow: score != null && score >= 65 ? "0 0 12px -2px rgba(34,211,238,0.25)" : "none",
      }}
    >
      {score != null && (
        <span className={`font-mono ${large ? "text-sm" : "text-[10px]"} font-medium text-white drop-shadow`}>
          {Math.round(score)}
        </span>
      )}
    </div>
  );
}

function ScaleLegend() {
  const buckets: { label: string; color: string }[] = [
    { label: "≥80", color: "rgba(52,211,153,0.85)" },
    { label: "65+", color: "rgba(34,211,238,0.85)" },
    { label: "50+", color: "rgba(251,191,36,0.85)" },
    { label: "30+", color: "rgba(251,113,133,0.85)" },
    { label: "<30", color: "rgba(244,63,94,0.85)" },
  ];
  return (
    <div className="inline-flex items-center gap-1 rounded-full border border-border bg-surface px-2 py-1 text-[10px] text-ink-muted">
      <span className="mr-1">分数</span>
      {buckets.map((b) => (
        <span key={b.label} className="inline-flex items-center gap-1 px-1">
          <span className="h-2 w-2 rounded-sm" style={{ backgroundColor: b.color }} />
          {b.label}
        </span>
      ))}
    </div>
  );
}
