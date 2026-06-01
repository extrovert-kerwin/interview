"use client";

import { motion } from "framer-motion";
import { ArrowRight, BookOpenCheck, Compass, Database, Loader2, Printer, RefreshCw, Scale, Sparkles } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { CommunicationAnalysis } from "@/components/CommunicationAnalysis";
import { CompetencyRadar } from "@/components/CompetencyRadar";
import { DimensionBreakdown } from "@/components/DimensionBreakdown";
import { HighlightList } from "@/components/HighlightList";
import { KnowledgeGraph } from "@/components/KnowledgeGraph";
import { QAReview } from "@/components/QAReview";
import { QuestionRubricGrid } from "@/components/QuestionRubricGrid";
import { ReportHero } from "@/components/ReportHero";
import { RiskFlags } from "@/components/RiskFlags";
import { finalize, FinalReport, getReport } from "@/lib/api";
import { useT } from "@/lib/i18n";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; report: FinalReport }
  | { kind: "pending"; message: string }
  | { kind: "missing"; message: string };

const PENDING_HINTS = ["尚未生成", "还没生成", "report not ready", "finalize"];

function classifyError(message: string): "pending" | "missing" {
  const lower = message.toLowerCase();
  return PENDING_HINTS.some((hint) => message.includes(hint) || lower.includes(hint)) ? "pending" : "missing";
}

export default function ReportPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const t = useT();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [generating, setGenerating] = useState(false);
  const pollRef = useRef<number | null>(null);

  const fetchReport = useCallback(async () => {
    if (!params.id) return;
    try {
      const report = await getReport(params.id);
      setState({ kind: "ready", report });
      if (pollRef.current) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    } catch (err: any) {
      const message = err?.message || "无法加载报告";
      const kind = classifyError(message);
      setState({ kind, message });
    }
  }, [params.id]);

  useEffect(() => {
    fetchReport();
  }, [fetchReport]);

  useEffect(() => {
    if (state.kind !== "pending") return;
    if (pollRef.current) return;
    pollRef.current = window.setInterval(fetchReport, 5000);
    return () => {
      if (pollRef.current) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [state.kind, fetchReport]);

  async function triggerFinalize() {
    if (!params.id || generating) return;
    setGenerating(true);
    toast.info(t("report.finalizeInfoToast"));
    try {
      await finalize(params.id);
      toast.success(t("report.finalizedToast"));
      await fetchReport();
    } catch (err: any) {
      toast.error(err?.message || t("report.finalizeFail"));
    } finally {
      setGenerating(false);
    }
  }

  if (state.kind === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center text-ink-muted">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
        {t("report.loading")}
      </div>
    );
  }

  if (state.kind === "pending") {
    return (
      <div className="mx-auto flex min-h-screen max-w-xl items-center px-6 py-16">
        <div className="glass-strong relative w-full overflow-hidden rounded-3xl p-10 text-center">
          <div className="noise-layer rounded-3xl" />
          <div className="mesh-orb mx-auto h-24 w-24 opacity-70" />
          <div className="-mt-16 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-accent-violet to-accent-cyan shadow-glow-soft">
            <Sparkles className="h-6 w-6 text-white" />
          </div>
          <h1 className="mt-5 text-2xl font-semibold">{t("report.pending.title")}</h1>
          <p className="mt-3 text-sm leading-7 text-ink-muted">
            {t("report.pending.body")}
          </p>
          <div className="mt-7 flex flex-col items-stretch gap-3 sm:flex-row sm:justify-center">
            <button
              onClick={triggerFinalize}
              disabled={generating}
              className="btn-glow tap-shrink shine-on-hover group inline-flex items-center justify-center gap-2 rounded-full px-6 py-3 text-sm font-medium"
            >
              {generating ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {t("report.pending.generating")}
                </>
              ) : (
                <>
                  {t("report.pending.go")}
                  <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
                </>
              )}
            </button>
            <button
              onClick={fetchReport}
              className="btn-soft tap-shrink inline-flex items-center justify-center gap-2 rounded-full px-5 py-3 text-sm"
            >
              <RefreshCw className="h-4 w-4" />
              {t("report.pending.retry")}
            </button>
          </div>
          <p className="mt-5 font-mono text-xs text-ink-dim">{params.id}</p>
        </div>
      </div>
    );
  }

  if (state.kind === "missing") {
    return (
      <div className="mx-auto flex min-h-screen max-w-xl items-center px-6 py-16">
        <div className="glass-strong relative w-full overflow-hidden rounded-3xl p-10 text-center">
          <div className="noise-layer rounded-3xl" />
          <h1 className="text-2xl font-semibold">{t("report.missing.title")}</h1>
          <p className="mt-3 text-sm leading-7 text-ink-muted">
            {t("report.missing.subtitle")}
          </p>
          <div className="mt-7 flex flex-col items-stretch gap-3 sm:flex-row sm:justify-center">
            <Link
              href="/records"
              className="btn-glow tap-shrink inline-flex items-center justify-center gap-2 rounded-full px-6 py-3 text-sm font-medium"
            >
              {t("report.missing.records")}
              <ArrowRight className="h-4 w-4" />
            </Link>
            <button
              onClick={() => router.push(`/interview/${params.id}`)}
              className="btn-soft tap-shrink inline-flex items-center justify-center gap-2 rounded-full px-5 py-3 text-sm"
            >
              <RefreshCw className="h-4 w-4" />
              {t("report.missing.backToInterview")}
            </button>
          </div>
          <p className="mt-5 font-mono text-xs text-ink-dim">{params.id}</p>
        </div>
      </div>
    );
  }

  const { report } = state;

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <div className="no-print flex justify-end">
        <button
          onClick={() => window.print()}
          className="btn-soft tap-shrink inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-sm"
        >
          <Printer className="h-4 w-4" />
          {t("report.print")}
        </button>
      </div>

      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="mt-6">
        <ReportHero
          score={report.overall_score}
          recommendation={report.recommendation}
          summary={report.summary}
          candidate={report.profile?.name}
          position={report.position}
          completion={report.completion}
        />
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.08 }} className="mt-6">
        <PersistedNotice id={params.id} />
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.1 }} className="mt-6 grid gap-6 lg:grid-cols-[0.9fr,1.1fr]">
        <CompetencyRadar dimensions={report.dimensions} />
        <DimensionBreakdown details={report.dimension_details} />
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.12 }} className="mt-6">
        <KnowledgeCoverage coverage={report.knowledge_coverage} />
      </motion.div>

      {report.knowledge_coverage && report.per_question?.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.13 }} className="mt-6">
          <KnowledgeGraph
            coverage={report.knowledge_coverage}
            perQuestion={report.per_question}
            position={report.position}
          />
        </motion.div>
      )}

      {report.per_question?.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.135 }} className="mt-6">
          <QuestionRubricGrid perQuestion={report.per_question} />
        </motion.div>
      )}

      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.14 }} className="mt-6">
        <RiskFlags flags={report.risk_flags} />
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.15 }} className="mt-6">
        <EvaluationMethodology methodology={report.evaluation_methodology} />
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.16 }} className="mt-6 grid gap-6 md:grid-cols-2">
        <HighlightList title="report.strengthsTitle" variant="strength" items={report.strengths || []} />
        <HighlightList title="report.gapsTitle" variant="gap" items={report.gaps || []} />
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.18 }} className="mt-6">
        <CommunicationAnalysis analysis={report.communication_analysis} />
      </motion.div>

      {report.next_steps?.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.2 }} className="glass-strong mt-6 rounded-2xl p-6">
          <div className="mb-4 flex items-center gap-2">
            <Compass className="h-4 w-4 text-accent-cyan" />
            <h3 className="text-base font-medium">{t("report.nextSteps.title")}</h3>
          </div>
          <ul className="space-y-3 text-sm">
            {report.next_steps.map((s, i) => (
              <li key={i} className="lift-hover flex items-start gap-3 rounded-xl border border-border bg-surface p-3">
                <span className="font-mono text-xs text-accent-cyan">{String(i + 1).padStart(2, "0")}</span>
                <span className="leading-relaxed">{s}</span>
              </li>
            ))}
          </ul>
        </motion.div>
      )}

      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.25 }} className="mt-6">
        <QAReview qaHistory={report.qa_history || []} evaluations={report.per_question || []} />
      </motion.div>

      <div className="mt-10 text-center text-xs text-ink-dim">
        {t("report.footer")}
      </div>
    </div>
  );
}

function PersistedNotice({ id }: { id: string }) {
  const t = useT();
  return (
    <div className="glass-strong flex flex-wrap items-center justify-between gap-3 rounded-2xl px-5 py-3.5 text-sm text-ink-muted">
      <span className="inline-flex items-center gap-2">
        <Database className="h-4 w-4 text-accent-emerald" />
        {t("report.persistedNotice")}
      </span>
      <span className="font-mono text-xs text-ink-dim">{id}</span>
    </div>
  );
}

function EvaluationMethodology({ methodology }: { methodology?: FinalReport["evaluation_methodology"] }) {
  const t = useT();
  if (!methodology) return null;
  const calibration = methodology.calibration || {};
  return (
    <section className="glass-strong rounded-2xl p-6">
      <div className="mb-4 flex items-center gap-2">
        <Scale className="h-4 w-4 text-accent-cyan" />
        <h2 className="text-base font-medium">{t("report.methodology.title")}</h2>
      </div>
      <p className="text-sm leading-relaxed text-ink-muted">{methodology.summary}</p>
      <div className="mt-4 grid gap-3 md:grid-cols-4">
        <MethodMetric label={t("report.methodology.evidence")} value={calibration.avg_evidence_quality} />
        <MethodMetric label={t("report.methodology.uncertainty")} value={calibration.avg_uncertainty} />
        <MethodMetric label={t("report.methodology.completion")} value={calibration.completion_rate != null ? Math.round(calibration.completion_rate * 100) : undefined} suffix="%" />
        <MethodMetric label={t("report.methodology.knowledge")} value={calibration.knowledge_score} />
      </div>
      <ul className="mt-4 grid gap-2 text-sm text-ink-muted md:grid-cols-3">
        {(methodology.principles || []).map((item) => (
          <li key={item} className="rounded-xl border border-border bg-surface p-3 leading-relaxed">
            {item}
          </li>
        ))}
      </ul>
    </section>
  );
}

function MethodMetric({ label, value, suffix = "" }: { label: string; value?: number; suffix?: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-3">
      <div className="text-xs text-ink-dim">{label}</div>
      <div className="mt-1 font-mono text-2xl text-ink">{value ?? "--"}{value != null ? suffix : ""}</div>
    </div>
  );
}

function KnowledgeCoverage({ coverage }: { coverage?: FinalReport["knowledge_coverage"] }) {
  const t = useT();
  if (!coverage) return null;
  const items = coverage.items || [];
  return (
    <section className="glass-strong rounded-2xl p-6">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <BookOpenCheck className="h-4 w-4 text-accent-cyan" />
            <h2 className="text-base font-medium">{t("report.coverage.title")}</h2>
          </div>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-ink-muted">{coverage.summary}</p>
        </div>
        <div className="text-right">
          <div className="font-mono text-3xl text-ink">{coverage.overall_score}</div>
          <div className="text-xs text-ink-dim">{t("report.coverage.summaryLabel")} {Math.round((coverage.coverage_rate || 0) * 100)}%</div>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        {items.slice(0, 8).map((item) => (
          <article key={item.name} className="lift-hover rounded-xl border border-border bg-surface p-4">
            <div className="mb-2 flex items-start justify-between gap-3">
              <div>
                <h3 className="text-sm font-medium text-ink">{item.name}</h3>
                <p className="mt-1 text-xs text-ink-dim">
                  {t("report.coverage.itemFmt", { level: item.level, answered: item.answered_count, planned: item.planned_count, avg: item.avg_score })}
                </p>
              </div>
              <span className="font-mono text-lg text-ink">{item.coverage_score}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full progress-track">
              <div className="h-full rounded-full bg-gradient-to-r from-accent-violet via-accent-cyan to-accent-emerald" style={{ width: `${Math.max(4, Math.min(100, item.coverage_score))}%` }} />
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
