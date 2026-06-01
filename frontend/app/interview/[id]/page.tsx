"use client";

import { motion } from "framer-motion";
import { RefreshCw, Send, SkipForward, Sparkles } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { AgentTimeline } from "@/components/AgentTimeline";
import { ChatMessage, ChatStream } from "@/components/ChatStream";
import { DigitalInterviewer } from "@/components/DigitalInterviewer";
import { ProgressPanel } from "@/components/ProgressPanel";
import { VideoAnalyzer } from "@/components/VideoAnalyzer";
import { SpeechMetrics, VoiceClip, VoiceRecorder } from "@/components/VoiceRecorder";
import { finalize, getSession, SessionSnapshot, skipQuestion, submitAnswer } from "@/lib/api";
import { useT } from "@/lib/i18n";

const streamedInitialQuestions = new Set<string>();

export default function InterviewPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const t = useT();
  const id = params.id;

  const [session, setSession] = useState<SessionSnapshot | null>(null);
  const [loadError, setLoadError] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [speechMetrics, setSpeechMetrics] = useState<SpeechMetrics | undefined>();
  const [voiceClip, setVoiceClip] = useState<VoiceClip | undefined>();
  const [thinking, setThinking] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [activeAgent, setActiveAgent] = useState<string | undefined>();
  const startedAtRef = useRef<number>(Date.now());

  const streamInAi = useCallback((text: string, kind: "main" | "follow_up", baseId: string) => {
    if (baseId.startsWith("initial-")) {
      if (streamedInitialQuestions.has(baseId)) return;
      streamedInitialQuestions.add(baseId);
    }
    const msgId = baseId.startsWith("initial-") ? baseId : `${baseId}-${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      {
        id: msgId,
        role: "ai",
        content: "",
        streaming: true,
        metaKey: kind === "follow_up" ? "interview.meta.followUp" : "interview.meta.interviewer",
      },
    ]);

    let i = 0;
    const total = text.length;
    const step = Math.max(1, Math.floor(total / 80));
    const tick = () => {
      i = Math.min(total, i + step);
      setMessages((prev) => prev.map((m) => (m.id === msgId ? { ...m, content: text.slice(0, i) } : m)));
      if (i < total) {
        setTimeout(tick, 18);
      } else {
        setMessages((prev) => prev.map((m) => (m.id === msgId ? { ...m, streaming: false, content: text } : m)));
      }
    };
    tick();
  }, []);

  const loadSession = useCallback(async () => {
    if (!id) return;
    try {
      setLoadError("");
      const snap = await getSession(id);
      setSession(snap);
      setActiveAgent(snap.last_active_agent);
      if (snap.pending_question) {
        streamInAi(snap.pending_question, snap.pending_kind, `initial-${id}`);
      }
    } catch (err: any) {
      setLoadError(t("interview.loadError"));
      toast.error(err?.message || t("interview.loadFailToast"));
    }
  }, [id, streamInAi, t]);

  useEffect(() => {
    loadSession();
  }, [loadSession]);

  const isDone = session?.stage === "evaluating" || session?.stage === "reporting" || session?.stage === "done";

  async function runFinalize(sid: string) {
    setFinalizing(true);
    toast.info(t("interview.finalizingToast"));
    try {
      await finalize(sid);
      toast.success(t("interview.reportReadyToast"));
      router.push(`/report/${sid}`);
    } catch (err: any) {
      toast.error(err?.message || t("interview.finalizeFail"));
      setFinalizing(false);
    }
  }

  const applyStepResponse = useCallback(
    async (res: {
      pending_question: string;
      pending_kind: "main" | "follow_up";
      current_q_index: number;
      stage: string;
      last_active_agent?: string;
      question_plan?: SessionSnapshot["question_plan"];
      done: boolean;
    }) => {
      setActiveAgent(res.last_active_agent);
      setSession((s) =>
        s
          ? {
              ...s,
              pending_question: res.pending_question,
              pending_kind: res.pending_kind,
              question_plan: res.question_plan ?? s.question_plan,
              current_q_index: res.current_q_index,
              stage: res.stage,
              last_active_agent: res.last_active_agent,
            }
          : s,
      );

      if (res.done && session) {
        setThinking(false);
        await runFinalize(session.session_id);
        return;
      }
      if (res.pending_question) {
        streamInAi(res.pending_question, res.pending_kind, `q-${res.current_q_index}`);
      }
    },
    [session, streamInAi],
  );

  const handleSend = useCallback(async () => {
    if (!session || !input.trim() || thinking || finalizing) return;
    const answer = input.trim();
    setInput("");
    const metrics = speechMetrics;
    const clip = voiceClip;
    setSpeechMetrics(undefined);
    setVoiceClip(undefined);
    setMessages((prev) => [
      ...prev,
      {
        id: `me-${Date.now()}`,
        role: "user",
        content: answer,
        audioUrl: clip?.url,
        audioDurationMs: clip?.durationMs,
        audioMimeType: clip?.mimeType,
        metaKey: clip ? "interview.meta.voiceAnswer" : undefined,
      },
    ]);
    setThinking(true);
    try {
      const res = await submitAnswer(session.session_id, answer, metrics);
      await applyStepResponse(res);
    } catch (err: any) {
      toast.error(err?.message || t("interview.submitFail"));
    } finally {
      setThinking(false);
    }
  }, [session, input, speechMetrics, voiceClip, thinking, finalizing, applyStepResponse, t]);

  const handleSkip = useCallback(async () => {
    if (!session || thinking || finalizing || isDone) return;
    setMessages((prev) => [...prev, { id: `skip-${Date.now()}`, role: "user", content: t("interview.skip.bubble") }]);
    setThinking(true);
    try {
      const res = await skipQuestion(session.session_id);
      await applyStepResponse(res);
    } catch (err: any) {
      toast.error(err?.message || t("interview.skipFail"));
    } finally {
      setThinking(false);
    }
  }, [session, thinking, finalizing, isDone, applyStepResponse, t]);

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSend();
    }
  }

  const total = session?.total_questions ?? 0;
  const current = session?.current_q_index ?? 0;
  const currentQuestion = session?.question_plan?.[current];
  const plannedKnowledge = session?.question_plan?.flatMap((q) => q.knowledge_points || []) ?? [];
  const uniqueKnowledge = Array.from(new Set(plannedKnowledge));

  return (
    <div className="mx-auto flex min-h-screen max-w-7xl flex-col px-6 py-6">
      <VideoAnalyzer sessionId={session?.session_id} disabled={Boolean(loadError) || isDone} />
      <div className="grid flex-1 grid-cols-12 gap-6">
        <motion.aside
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4 }}
          className="order-2 col-span-12 md:order-1 md:col-span-3"
        >
          <AgentTimeline agents={session?.agents ?? []} active={activeAgent} stage={session?.stage} />
          {session?.profile && (
            <div className="glass-strong mt-5 rounded-2xl p-4 text-sm">
              <div className="mb-2 text-xs uppercase tracking-wider text-ink-dim">{t("interview.aside.candidate")}</div>
              <div className="space-y-1">
                <div className="font-medium">{session.profile.name}</div>
                {session.profile.current_title && <div className="text-xs text-ink-muted">{session.profile.current_title}</div>}
                {session.profile.skills && session.profile.skills.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 pt-2">
                    {session.profile.skills.slice(0, 6).map((s) => (
                      <span key={s} className="rounded-full border border-border bg-surface px-2 py-0.5 text-[10px] text-ink-muted">
                        {s}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </motion.aside>

        <motion.section
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="order-1 col-span-12 flex flex-col md:order-2 md:col-span-6"
        >
          <div className="glass-strong flex h-[68vh] flex-col rounded-2xl p-4 md:h-[72vh]">
            <DigitalInterviewer text={session?.pending_question} disabled={Boolean(loadError) || isDone} />
            {loadError && (
              <div className="m-auto flex max-w-sm flex-col items-center gap-4 text-center">
                <p className="text-sm leading-relaxed text-ink-muted">{loadError}</p>
                <button
                  onClick={loadSession}
                  className="btn-soft tap-shrink inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  {t("interview.tryAgain")}
                </button>
              </div>
            )}
            {!loadError && session && messages.length === 0 && (
              <div className="m-auto max-w-sm text-center text-sm leading-relaxed text-ink-muted">
                {t("interview.preparing")}
              </div>
            )}
            <ChatStream messages={messages} thinking={thinking || finalizing} />
          </div>

          <div className="glass-strong mt-4 rounded-2xl p-3">
            <div className="flex items-end gap-2">
              <VoiceRecorder
                sessionId={session?.session_id}
                disabled={thinking || finalizing || isDone}
                onTranscript={(text, metrics, clip) => {
                  setSpeechMetrics(metrics);
                  setVoiceClip(clip);
                  setInput((prev) => (prev ? `${prev} ${text}` : text));
                }}
              />
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={isDone ? t("interview.placeholder.done") : t("interview.placeholder.input")}
                disabled={thinking || finalizing || isDone}
                rows={2}
                className="flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-relaxed text-ink placeholder:text-ink-dim focus:outline-none disabled:opacity-50"
              />
              <button
                onClick={handleSend}
                disabled={thinking || finalizing || !input.trim() || isDone}
                className="btn-glow tap-shrink inline-flex h-10 items-center gap-1.5 rounded-full px-4 text-sm font-medium"
              >
                <Send className="h-4 w-4" />
                {t("interview.send")}
              </button>
              <button
                onClick={handleSkip}
                disabled={thinking || finalizing || isDone || !session}
                title={t("interview.skip.tip")}
                className="btn-soft tap-shrink inline-flex h-10 items-center gap-1.5 rounded-full px-3 text-sm"
              >
                <SkipForward className="h-4 w-4" />
                {t("interview.skip")}
              </button>
            </div>
          </div>
        </motion.section>

        <motion.aside
          initial={{ opacity: 0, x: 10 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4 }}
          className="order-3 col-span-12 md:col-span-3"
        >
          <ProgressPanel current={current} total={total} startedAt={startedAtRef.current} />
          <KnowledgePanel
            currentCategory={currentQuestion?.category}
            currentIntent={currentQuestion?.intent}
            currentPoints={currentQuestion?.knowledge_points || []}
            allPoints={uniqueKnowledge}
          />
          <div className="glass-strong mt-5 rounded-2xl p-4">
            <div className="mb-3 flex items-center gap-1.5 text-xs uppercase tracking-wider text-ink-dim">
              <Sparkles className="h-3.5 w-3.5 text-accent-cyan" />
              {t("interview.tips.title")}
            </div>
            <ul className="space-y-2 text-xs leading-relaxed text-ink-muted">
              <li>{t("interview.tips.1")}</li>
              <li>{t("interview.tips.2")}</li>
              <li>{t("interview.tips.3")}</li>
            </ul>
          </div>
        </motion.aside>
      </div>
    </div>
  );
}

function KnowledgePanel({
  currentCategory,
  currentIntent,
  currentPoints,
  allPoints,
}: {
  currentCategory?: string;
  currentIntent?: string;
  currentPoints: string[];
  allPoints: string[];
}) {
  const t = useT();
  return (
    <div className="glass-strong mt-5 rounded-2xl p-4">
      <div className="mb-3 text-xs uppercase tracking-wider text-ink-dim">{t("interview.kp.title")}</div>
      {currentPoints.length > 0 ? (
        <>
          <div className="mb-2 text-sm font-medium text-ink">{currentCategory || t("interview.kp.currentDefault")}</div>
          {currentIntent && <p className="mb-3 text-xs leading-relaxed text-ink-muted">{currentIntent}</p>}
          <div className="flex flex-wrap gap-2">
            {currentPoints.map((point) => (
              <span key={point} className="rounded-full border border-accent-cyan/30 bg-accent-cyan/10 px-2.5 py-1 text-xs text-accent-cyan">
                {point}
              </span>
            ))}
          </div>
        </>
      ) : (
        <p className="text-xs leading-relaxed text-ink-muted">{t("interview.kp.placeholder")}</p>
      )}
      {allPoints.length > currentPoints.length && (
        <div className="mt-4 border-t border-border pt-3">
          <div className="mb-2 text-[10px] uppercase tracking-wider text-ink-dim">{t("interview.kp.allTitle")}</div>
          <div className="flex flex-wrap gap-1.5">
            {allPoints.slice(0, 10).map((point) => (
              <span key={point} className="rounded-full border border-border bg-surface px-2 py-0.5 text-[10px] text-ink-muted">
                {point}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
