"use client";

import { Check, CircleDot } from "lucide-react";

import { useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const AGENT_LABELS: Record<string, { name: string; desc: string }> = {
  InterviewAgent: { name: "AI Interview", desc: "加油" },
  ResumeParserAgent: { name: "Resume Parser", desc: "Parse resume profile" },
  QuestionPlannerAgent: {
    name: "Question Planner",
    desc: "Create question plan",
  },
  InterviewerAgent: { name: "Interviewer", desc: "Run interview" },
  FollowUpAgent: { name: "Follow-up", desc: "Judge follow-up" },
  EvaluatorAgent: { name: "Evaluator", desc: "Score answers" },
  ReporterAgent: { name: "Reporter", desc: "Build report" },
};

interface Props {
  agents: string[];
  active?: string;
  stage?: string;
}

const STAGE_ORDER = [
  "parsing",
  "planning",
  "interviewing",
  "evaluating",
  "reporting",
  "done",
];

export function AgentTimeline({ agents, active, stage }: Props) {
  const t = useT();
  const stageIdx = stage ? STAGE_ORDER.indexOf(stage) : -1;

  return (
    <div className="space-y-3">
      <div className="text-xs uppercase tracking-wider text-ink-dim">
        {t("agents.header")}
      </div>
      <div className="space-y-2">
        {agents.map((agent) => {
          const isActive = active === agent;
          const isDone =
            (stageIdx >= 0 && stageIdx > getAgentStageIdx(agent)) ||
            stage === "done";

          return (
            <div
              key={agent}
              className={cn(
                "glass relative flex items-start gap-3 rounded-xl border p-3 transition",
                isActive
                  ? "border-accent-violet/40 shadow-glow"
                  : "border-border"
              )}
            >
              <div
                className={cn(
                  "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border",
                  isActive
                    ? "border-accent-violet/60 bg-accent-violet/15 text-accent-violet"
                    : isDone
                    ? "border-accent-emerald/40 bg-accent-emerald/10 text-accent-emerald"
                    : "border-border bg-surface text-ink-dim"
                )}
              >
                {isDone && !isActive ? (
                  <Check className="h-3.5 w-3.5" />
                ) : (
                  <CircleDot
                    className={cn("h-3.5 w-3.5", isActive && "animate-pulse")}
                  />
                )}
              </div>
              <div className="min-w-0">
                <div className="text-sm font-medium">
                  {AGENT_LABELS[agent]?.name || agent}
                </div>
                <div className="truncate text-xs text-ink-muted">
                  {AGENT_LABELS[agent]?.desc}
                </div>
              </div>
              {isActive && (
                <span className="absolute right-3 top-3 text-[10px] uppercase tracking-wider text-accent-violet">
                  {t("agents.active")}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function getAgentStageIdx(agent: string): number {
  switch (agent) {
    case "InterviewAgent":
      return STAGE_ORDER.indexOf("parsing");
    case "ResumeParserAgent":
      return STAGE_ORDER.indexOf("parsing");
    case "QuestionPlannerAgent":
      return STAGE_ORDER.indexOf("planning");
    case "InterviewerAgent":
    case "FollowUpAgent":
      return STAGE_ORDER.indexOf("interviewing");
    case "EvaluatorAgent":
      return STAGE_ORDER.indexOf("evaluating");
    case "ReporterAgent":
      return STAGE_ORDER.indexOf("reporting");
    default:
      return -1;
  }
}
