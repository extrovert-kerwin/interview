"use client";

import { useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const POSITIONS = [
  { value: "前端工程师", labelKey: "picker.pos.frontend" },
  { value: "后端工程师", labelKey: "picker.pos.backend" },
  { value: "全栈工程师", labelKey: "picker.pos.fullstack" },
  { value: "算法 / AI 工程师", labelKey: "picker.pos.ai" },
  { value: "数据工程师", labelKey: "picker.pos.data" },
  { value: "移动端工程师", labelKey: "picker.pos.mobile" },
  { value: "测试工程师", labelKey: "picker.pos.qa" },
  { value: "产品经理", labelKey: "picker.pos.pm" },
] as const;

const DIFFICULTIES = [
  { value: "junior", labelKey: "picker.diff.junior", descKey: "picker.diff.juniorDesc" },
  { value: "mid", labelKey: "picker.diff.mid", descKey: "picker.diff.midDesc" },
  { value: "senior", labelKey: "picker.diff.senior", descKey: "picker.diff.seniorDesc" },
] as const;

interface Props {
  position: string;
  difficulty: string;
  onPosition: (v: string) => void;
  onDifficulty: (v: string) => void;
}

export function PositionPicker({
  position,
  difficulty,
  onPosition,
  onDifficulty,
}: Props) {
  const t = useT();
  return (
    <div className="space-y-6">
      <div>
        <div className="mb-3 text-xs uppercase tracking-wider text-ink-dim">
          {t("picker.position")}
        </div>
        <div className="flex flex-wrap gap-2">
          {POSITIONS.map((p) => (
            <button
              key={p.value}
              type="button"
              onClick={() => onPosition(p.value)}
              className={cn(
                "rounded-full border px-4 py-1.5 text-sm transition",
                position === p.value
                  ? "border-accent-violet/60 bg-accent-violet/10 text-ink shadow-glow"
                  : "border-border bg-surface text-ink-muted hover:border-ink/30 hover:text-ink",
              )}
            >
              {t(p.labelKey)}
            </button>
          ))}
        </div>
      </div>

      <div>
        <div className="mb-3 text-xs uppercase tracking-wider text-ink-dim">
          {t("picker.difficulty")}
        </div>
        <div className="grid grid-cols-3 gap-3">
          {DIFFICULTIES.map((d) => (
            <button
              key={d.value}
              type="button"
              onClick={() => onDifficulty(d.value)}
              className={cn(
                "glass rounded-xl px-4 py-3 text-left transition",
                difficulty === d.value
                  ? "border-accent-cyan/40 shadow-glow-cyan"
                  : "hover:border-ink/30",
              )}
            >
              <div className="text-base font-medium">{t(d.labelKey)}</div>
              <div className="mt-0.5 text-xs text-ink-muted">{t(d.descKey)}</div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
