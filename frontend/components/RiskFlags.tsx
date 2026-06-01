"use client";

import { AlertTriangle, Info, ShieldAlert } from "lucide-react";

import type { RiskFlag } from "@/lib/api";
import { useT } from "@/lib/i18n";

interface Props {
  flags?: RiskFlag[];
}

const STYLE: Record<string, string> = {
  high: "border-rose-400/30 bg-rose-500/[0.08] text-rose-200",
  medium: "border-amber-400/30 bg-amber-500/[0.08] text-amber-200",
  low: "border-cyan-400/25 bg-cyan-500/[0.08] text-cyan-200",
};

export function RiskFlags({ flags }: Props) {
  const t = useT();
  if (!flags?.length) return null;
  return (
    <section className="glass rounded-2xl p-6">
      <div className="mb-4 flex items-center gap-2">
        <ShieldAlert className="h-4 w-4 text-amber-300" />
        <h2 className="text-base font-medium">{t("risk.title")}</h2>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {flags.map((flag, index) => (
          <article
            key={`${flag.title}-${index}`}
            className={`rounded-2xl border p-4 ${STYLE[flag.level] || STYLE.low}`}
          >
            <div className="mb-2 flex items-center gap-2">
              {flag.level === "high" ? <AlertTriangle className="h-4 w-4" /> : <Info className="h-4 w-4" />}
              <h3 className="font-medium">{flag.title}</h3>
            </div>
            <p className="text-sm leading-relaxed text-ink-muted">{flag.detail}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
