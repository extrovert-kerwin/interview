"use client";

import { CheckCircle2, TrendingUp } from "lucide-react";

import { useT } from "@/lib/i18n";

interface Props {
  title: string;
  variant: "strength" | "gap";
  items: string[];
}

export function HighlightList({ title, variant, items }: Props) {
  const t = useT();
  const isStrength = variant === "strength";
  const Icon = isStrength ? CheckCircle2 : TrendingUp;
  const color = isStrength ? "text-accent-emerald" : "text-accent-amber";

  return (
    <div className="glass rounded-2xl p-6">
      <div className="mb-4 flex items-center gap-2">
        <Icon className={`h-4 w-4 ${color}`} />
        <h3 className="text-base font-medium">{t(title)}</h3>
      </div>
      <ul className="space-y-3">
        {items.length === 0 && <li className="text-sm text-ink-muted">{t("highlight.empty")}</li>}
        {items.map((it, i) => (
          <li key={i} className="flex items-start gap-3 rounded-xl border border-border bg-surface p-3 text-sm leading-relaxed text-ink">
            <span className={`mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full ${isStrength ? "bg-accent-emerald" : "bg-accent-amber"}`} />
            <span>{it}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
