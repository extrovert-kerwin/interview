"use client";

import { motion } from "framer-motion";
import {
  ArrowRight,
  BarChart3,
  BookOpenCheck,
  FileText,
  History,
  MessagesSquare,
  Sparkles,
  Video,
} from "lucide-react";
import Link from "next/link";

import { CountUp } from "@/components/CountUp";
import { KeywordMarquee } from "@/components/KeywordMarquee";
import { Spotlight } from "@/components/Spotlight";
import { useT } from "@/lib/i18n";

const STEPS = [
  {
    titleKey: "home.step1.title",
    descKey: "home.step1.desc",
    chipKey: "home.step1.chip",
    icon: FileText,
    accent: "from-accent-violet to-accent-cyan",
  },
  {
    titleKey: "home.step2.title",
    descKey: "home.step2.desc",
    chipKey: "home.step2.chip",
    icon: MessagesSquare,
    accent: "from-accent-cyan to-accent-emerald",
  },
  {
    titleKey: "home.step3.title",
    descKey: "home.step3.desc",
    chipKey: "home.step3.chip",
    icon: History,
    accent: "from-accent-emerald to-accent-amber",
  },
] as const;

const METRICS = [
  { labelKey: "home.metric1.label", subKey: "home.metric1.sub", value: 8, suffix: "" },
  { labelKey: "home.metric2.label", subKey: "home.metric2.sub", value: 10, suffix: "+" },
  { labelKey: "home.metric3.label", subKey: "home.metric3.sub", value: 100, suffix: "%" },
] as const;

export default function HomePage() {
  const t = useT();
  return (
    <div className="mx-auto min-h-screen max-w-7xl px-6 py-10">
      <section className="grid min-h-[calc(100vh-8rem)] items-center gap-12 lg:grid-cols-[1.08fr,0.92fr]">
        <motion.div
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: "easeOut" }}
        >
          <div className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-4 py-1.5 text-xs text-ink-muted backdrop-blur">
            <span className="relative inline-flex h-1.5 w-1.5">
              <span className="absolute inset-0 animate-ping rounded-full bg-accent-cyan opacity-70" />
              <span className="relative inline-block h-1.5 w-1.5 rounded-full bg-accent-cyan" />
            </span>
            {t("home.tag")}
          </div>

          <h1 className="mt-7 max-w-4xl text-display-sm font-semibold text-display-tight md:text-display lg:text-display-lg">
            {t("home.title.before")}
            <span className="text-brand">{t("home.title.brand")}</span>
          </h1>

          <p className="mt-7 max-w-2xl text-base leading-8 text-ink-muted md:text-lg">
            {t("home.subtitle")}
          </p>

          <div className="mt-9 flex flex-col gap-3 sm:flex-row">
            <div className="relative">
              <Link
                href="/upload"
                className="btn-glow glow-halo tap-shrink shine-on-hover group inline-flex items-center justify-center gap-2 rounded-full px-7 py-3.5 text-sm font-medium"
              >
                {t("home.cta.start")}
                <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
              </Link>
            </div>
            <Link
              href="/records"
              className="btn-soft tap-shrink inline-flex items-center justify-center rounded-full px-7 py-3.5 text-sm"
            >
              {t("home.cta.records")}
            </Link>
          </div>

          <div className="mt-12 grid gap-3 sm:grid-cols-3">
            {METRICS.map((item, i) => (
              <motion.div
                key={item.labelKey}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: 0.2 + i * 0.08, ease: "easeOut" }}
                className="glass-strong lift-hover group relative overflow-hidden rounded-2xl p-5"
              >
                <div className="absolute -right-8 -top-8 h-24 w-24 rounded-full bg-gradient-to-br from-accent-violet/30 to-accent-cyan/20 blur-2xl transition-opacity group-hover:opacity-80" />
                <div className="relative font-mono text-3xl text-ink md:text-4xl">
                  <CountUp to={item.value} suffix={item.suffix} duration={1400 + i * 150} />
                </div>
                <div className="relative mt-2 text-sm font-medium text-ink">{t(item.labelKey)}</div>
                <div className="relative mt-1 text-xs text-ink-dim">{t(item.subKey)}</div>
              </motion.div>
            ))}
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.97, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ duration: 0.65, delay: 0.1, ease: "easeOut" }}
          className="relative"
        >
          <div className="mesh-orb absolute -inset-8 -z-10 opacity-50" />

          <Spotlight className="glass-strong shimmer-border tilt-hover overflow-hidden rounded-3xl p-6">
            <div className="noise-layer rounded-3xl" />
            <div className="flex items-center justify-between border-b border-border pb-4">
              <div>
                <div className="text-sm font-medium text-ink">{t("home.preview.title")}</div>
                <div className="mt-1 text-xs text-ink-dim">{t("home.preview.subtitle")}</div>
              </div>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-accent-emerald/30 bg-accent-emerald/10 px-3 py-1 text-xs font-medium text-accent-emerald">
                <span className="relative inline-flex h-1.5 w-1.5">
                  <span className="absolute inset-0 animate-ping rounded-full bg-accent-emerald" />
                  <span className="relative inline-block h-1.5 w-1.5 rounded-full bg-accent-emerald" />
                </span>
                {t("home.preview.live")}
              </span>
            </div>

            <div className="mt-5 rounded-2xl border border-border bg-surface p-5">
              <div className="flex items-center gap-3">
                <div className="gradient-ring animate-float flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-accent-violet via-accent-cyan to-accent-emerald text-base font-semibold text-white shadow-glow-soft">
                  AI
                </div>
                <div>
                  <div className="text-sm font-medium">{t("home.preview.interviewer")}</div>
                  <div className="text-xs text-ink-dim">{t("home.preview.designingQ")}</div>
                </div>
              </div>
              <p className="mt-4 text-sm leading-7 text-ink-muted">
                {t("home.preview.sampleQ")}
              </p>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <Signal icon={BookOpenCheck} label={t("home.preview.signal.kp")} value={t("home.preview.signal.kpValue")} tint="violet" />
              <Signal icon={Video} label={t("home.preview.signal.video")} value={t("home.preview.signal.videoValue")} tint="emerald" />
              <Signal icon={BarChart3} label={t("home.preview.signal.voice")} value="82" tint="cyan" />
            </div>

            <div className="mt-4 rounded-2xl border border-border bg-surface p-5">
              <div className="mb-4 flex items-center gap-2 text-sm font-medium">
                <Sparkles className="h-4 w-4 text-accent-cyan" />
                {t("home.preview.summary")}
              </div>
              <div className="space-y-3 text-sm text-ink-muted">
                <Row label={t("home.preview.row.systemDesign")} value={76} from="from-accent-violet" to="to-accent-cyan" />
                <Row label={t("home.preview.row.knowledge")} value={68} from="from-accent-cyan" to="to-accent-emerald" />
                <Row label={t("home.preview.row.communication")} value={84} from="from-accent-emerald" to="to-accent-amber" />
              </div>
            </div>
          </Spotlight>
        </motion.div>
      </section>

      <motion.div
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true, amount: 0.4 }}
        transition={{ duration: 0.8 }}
        className="my-10"
      >
        <KeywordMarquee />
      </motion.div>

      <div className="divider-glow my-8" />

      <section className="grid gap-5 pb-16 pt-2 lg:grid-cols-3">
        {STEPS.map((step, i) => (
          <motion.div
            key={step.titleKey}
            initial={{ opacity: 0, y: 22 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.35 }}
            transition={{ duration: 0.5, delay: i * 0.08 }}
          >
            <Spotlight className="glass-strong lift-hover shine-on-hover group relative h-full overflow-hidden rounded-3xl p-7">
              <div className="noise-layer rounded-3xl" />
              <div
                className={`absolute -right-12 -top-12 h-32 w-32 rounded-full bg-gradient-to-br ${step.accent} opacity-25 blur-2xl transition-opacity group-hover:opacity-50`}
              />
              <div className="relative flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div
                    className={`gradient-ring rounded-2xl bg-gradient-to-br ${step.accent} p-2.5 shadow-glow-soft`}
                  >
                    <step.icon className="h-5 w-5 text-white" />
                  </div>
                  <span className="font-mono text-xs tracking-wider text-ink-dim">
                    STEP 0{i + 1}
                  </span>
                </div>
                <span
                  className={`rounded-full bg-gradient-to-r ${step.accent} px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-white opacity-90`}
                >
                  {t(step.chipKey)}
                </span>
              </div>
              <h3 className="relative mt-5 text-xl font-semibold">{t(step.titleKey)}</h3>
              <p className="relative mt-3 text-sm leading-7 text-ink-muted">{t(step.descKey)}</p>
              <div
                className={`absolute inset-x-7 bottom-0 h-px bg-gradient-to-r ${step.accent} opacity-0 transition-opacity duration-500 group-hover:opacity-70`}
              />
            </Spotlight>
          </motion.div>
        ))}
      </section>
    </div>
  );
}

function Signal({
  icon: Icon,
  label,
  value,
  tint,
}: {
  icon: typeof Video;
  label: string;
  value: string;
  tint: "violet" | "cyan" | "emerald";
}) {
  const tintMap = {
    violet: "text-accent-violet group-hover:border-accent-violet/40",
    cyan: "text-accent-cyan group-hover:border-accent-cyan/40",
    emerald: "text-accent-emerald group-hover:border-accent-emerald/40",
  };
  return (
    <div className={`group rounded-2xl border border-border bg-surface p-3.5 transition ${tintMap[tint].split(" ")[1]}`}>
      <Icon className={`h-4 w-4 ${tintMap[tint].split(" ")[0]}`} />
      <div className="mt-3 text-xs text-ink-dim">{label}</div>
      <div className="mt-1 text-sm font-medium text-ink">{value}</div>
    </div>
  );
}

function Row({
  label,
  value,
  from,
  to,
}: {
  label: string;
  value: number;
  from: string;
  to: string;
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <span>{label}</span>
        <span className="font-mono text-ink">
          <CountUp to={value} duration={1100} />
        </span>
      </div>
      <div className="progress-track h-2 overflow-hidden rounded-full">
        <motion.div
          initial={{ width: 0 }}
          whileInView={{ width: `${value}%` }}
          viewport={{ once: true, amount: 0.4 }}
          transition={{ duration: 1.1, ease: "easeOut", delay: 0.3 }}
          className={`h-full rounded-full bg-gradient-to-r ${from} ${to}`}
        />
      </div>
    </div>
  );
}
