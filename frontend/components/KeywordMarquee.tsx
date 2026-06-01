"use client";

const items = [
  "RAG · 检索增强",
  "Agent · 多智能体",
  "LangGraph",
  "系统设计",
  "推理与逻辑",
  "Vector DB",
  "云原生",
  "可观测性",
  "评估与对齐",
  "多模态",
  "前端工程化",
  "性能优化",
];

const accents = [
  "text-accent-violet",
  "text-accent-cyan",
  "text-accent-emerald",
  "text-accent-amber",
  "text-accent-rose",
];

export function KeywordMarquee() {
  return (
    <div className="marquee relative py-3" aria-hidden>
      <div className="marquee-track">
        {[...items, ...items].map((label, i) => (
          <span
            key={`${label}-${i}`}
            className={`inline-flex items-center gap-2 text-sm font-medium tracking-wide ${
              accents[i % accents.length]
            } whitespace-nowrap`}
          >
            <span className="h-1.5 w-1.5 rounded-full bg-current opacity-60" />
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}
