"use client";

import { useEffect, useState } from "react";
import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from "recharts";

import { useT } from "@/lib/i18n";

interface Props {
  dimensions: Record<string, number>;
}

function useChartColors() {
  const [colors, setColors] = useState({ grid: "rgba(255,255,255,0.08)", tick: "#9696a8" });

  useEffect(() => {
    const update = () => {
      const style = getComputedStyle(document.documentElement);
      const grid = style.getPropertyValue("--chart-grid").trim();
      const tick = style.getPropertyValue("--chart-tick").trim();
      if (grid && tick) setColors({ grid, tick });
    };
    update();
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  return colors;
}

export function CompetencyRadar({ dimensions }: Props) {
  const t = useT();
  const data = Object.entries(dimensions).map(([dimension, score]) => ({
    dimension,
    score,
  }));
  const { grid, tick } = useChartColors();

  return (
    <div className="glass rounded-2xl p-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className="text-xs uppercase tracking-wider text-ink-dim">
            {t("radar.captionEn")}
          </div>
          <h3 className="mt-1 text-lg font-medium">{t("radar.title")}</h3>
        </div>
      </div>
      <div className="h-[320px]">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={data} outerRadius="75%">
            <defs>
              <linearGradient id="radarGrad" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#a78bfa" stopOpacity={0.9} />
                <stop offset="100%" stopColor="#22d3ee" stopOpacity={0.6} />
              </linearGradient>
            </defs>
            <PolarGrid stroke={grid} />
            <PolarAngleAxis dataKey="dimension" tick={{ fill: tick, fontSize: 12 }} />
            <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fill: tick, fontSize: 10 }} tickCount={5} axisLine={false} />
            <Radar dataKey="score" stroke="#a78bfa" fill="url(#radarGrad)" fillOpacity={0.55} strokeWidth={2} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2 text-sm md:grid-cols-5">
        {data.map((d) => (
          <div key={d.dimension} className="rounded-lg border border-border bg-surface px-3 py-2">
            <div className="text-xs text-ink-muted">{d.dimension}</div>
            <div className="mt-1 font-mono text-lg tabular-nums">{d.score}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
