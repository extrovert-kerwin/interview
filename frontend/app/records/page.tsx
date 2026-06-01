"use client";

import { motion } from "framer-motion";
import { ArrowRight, FileText, Loader2, Plus, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Spotlight } from "@/components/Spotlight";
import { InterviewRecord, listMySessions } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function RecordsPage() {
  const router = useRouter();
  const t = useT();
  const [items, setItems] = useState<InterviewRecord[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        setItems(await listMySessions());
      } catch (err: any) {
        toast.error(err?.message || t("records.errorToast"));
        router.push("/login?next=/records");
      } finally {
        setLoading(false);
      }
    })();
  }, [router, t]);

  return (
    <div className="mx-auto min-h-screen max-w-5xl px-6 py-12">
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.55, ease: "easeOut" }}
        className="flex flex-wrap items-end justify-between gap-4"
      >
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-4 py-1.5 text-xs text-ink-muted">
            <Sparkles className="h-3.5 w-3.5 text-accent-cyan" />
            {t("records.tag")}
          </div>
          <h1 className="mt-5 text-display-sm font-semibold text-display-tight md:text-display">
            {t("records.title.before")}<span className="text-brand">{t("records.title.brand")}</span>
          </h1>
          <p className="mt-4 text-base leading-7 text-ink-muted">
            {t("records.subtitle")}
          </p>
        </div>
        <Link
          href="/upload"
          className="btn-glow tap-shrink shine-on-hover group inline-flex items-center gap-2 rounded-full px-5 py-3 text-sm font-medium"
        >
          <Plus className="h-4 w-4" />
          {t("records.cta.again")}
        </Link>
      </motion.div>

      {loading ? (
        <div className="mt-24 flex items-center justify-center text-ink-muted">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" />
          {t("records.loading")}
        </div>
      ) : items.length === 0 ? (
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, delay: 0.15 }}
          className="glass-strong mt-10 rounded-3xl p-12 text-center"
        >
          <div className="mesh-orb mx-auto h-24 w-24 opacity-70" />
          <div className="-mt-16 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-accent-violet to-accent-cyan shadow-glow-soft">
            <FileText className="h-6 w-6 text-white" />
          </div>
          <h2 className="mt-5 text-xl font-semibold">{t("records.empty.title")}</h2>
          <p className="mt-3 text-sm leading-7 text-ink-muted">
            {t("records.empty.desc")}
          </p>
          <Link
            href="/upload"
            className="btn-glow tap-shrink group mt-6 inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-medium"
          >
            {t("records.empty.cta")}
            <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
          </Link>
        </motion.div>
      ) : (
        <div className="mt-10 grid gap-4">
          {items.map((item, index) => (
            <motion.div
              key={item.session_id}
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.45, delay: index * 0.04 }}
            >
            <Spotlight className="glass-strong lift-hover group relative overflow-hidden rounded-2xl p-6">
              <div className="noise-layer rounded-2xl" />
              <div className="relative flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-lg font-semibold">{item.position || t("shell.recent.position.generic")}</h2>
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-xs ${stageClass(item.stage)}`}
                    >
                      {stageLabel(item.stage, t)}
                    </span>
                    {item.recommendation && (
                      <span className="rounded-full border border-accent-cyan/30 bg-accent-cyan/10 px-2.5 py-0.5 text-xs text-accent-cyan">
                        {item.recommendation}
                      </span>
                    )}
                  </div>
                  <p className="mt-2 text-sm text-ink-muted">
                    {item.candidate} · {new Date(item.updated_at).toLocaleString()}
                  </p>
                  <p className="mt-1 truncate font-mono text-xs text-ink-dim">
                    {item.session_id}
                  </p>
                </div>
                <div className="flex items-center gap-4">
                  {item.score != null && (
                    <div className="text-right">
                      <div className="font-mono text-3xl text-ink">{item.score}</div>
                      <div className="text-[10px] uppercase tracking-wider text-ink-dim">{t("records.total")}</div>
                    </div>
                  )}
                  <Link
                    href={
                      item.report_ready
                        ? `/report/${item.session_id}`
                        : `/interview/${item.session_id}`
                    }
                    className={`tap-shrink inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-medium transition ${
                      item.report_ready ? "btn-glow" : "btn-soft"
                    }`}
                  >
                    {item.report_ready ? t("records.viewReport") : t("records.continue")}
                    <ArrowRight className="h-3.5 w-3.5 transition group-hover:translate-x-0.5" />
                  </Link>
                </div>
              </div>
            </Spotlight>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}

function stageLabel(stage: string, t: (key: string) => string) {
  if (stage === "done") return t("records.stage.done");
  if (stage === "evaluating" || stage === "reporting") return t("records.stage.evaluating");
  if (stage === "interviewing") return t("records.stage.interviewing");
  return t("records.stage.created");
}

function stageClass(stage: string) {
  if (stage === "done") return "border border-accent-emerald/30 bg-accent-emerald/10 text-accent-emerald";
  if (stage === "evaluating" || stage === "reporting")
    return "border border-accent-amber/30 bg-accent-amber/10 text-accent-amber";
  if (stage === "interviewing")
    return "border border-accent-cyan/30 bg-accent-cyan/10 text-accent-cyan";
  return "border border-border text-ink-muted";
}
