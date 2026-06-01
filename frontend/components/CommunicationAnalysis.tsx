"use client";

import { Camera, Gauge, MessageSquareText, Mic2, Volume2 } from "lucide-react";

import { useT } from "@/lib/i18n";

interface SignalDimension {
  name: string;
  score?: number | null;
  level: string;
  insight: string;
}

interface Props {
  analysis?: {
    text?: string;
    audio?: string;
    video?: string;
    audio_dimensions?: SignalDimension[];
    video_dimensions?: SignalDimension[];
    metrics?: {
      voice_answer_count: number;
      audio_sample_count?: number;
      avg_duration_seconds?: number;
      avg_confidence?: number;
      avg_words_per_minute?: number;
      avg_volume?: number;
      peak_volume?: number;
      silence_rate?: number;
      volume_stability?: number;
      fluency_score?: number;
      nervousness_score?: number;
      confidence_score?: number;
      pace_label?: string;
    };
    video_metrics?: {
      sample_count: number;
      presence_rate?: number;
      avg_brightness?: number;
      avg_motion_proxy?: number;
      avg_face_count?: number;
      avg_attention_score?: number;
      center_rate?: number;
      lighting_quality?: string;
      motion_quality?: string;
      visual_nervousness_score?: number;
      presence_score?: number;
      framing_score?: number;
      lighting_score?: number;
    };
  };
}

export function CommunicationAnalysis({ analysis }: Props) {
  const t = useT();
  if (!analysis) return null;
  const metrics = analysis.metrics;
  const video = analysis.video_metrics;
  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-3">
        <Panel icon={<MessageSquareText className="h-4 w-4 text-accent-violet" />} title={t("comm.text")}>
          {analysis.text || t("comm.noText")}
        </Panel>
        <Panel icon={<Mic2 className="h-4 w-4 text-accent-cyan" />} title={t("comm.audio")}>
          <p>{analysis.audio || t("comm.noAudio")}</p>
          {metrics && (
            <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
              <Metric label={t("comm.m.asrAnswers")} value={String(metrics.voice_answer_count ?? 0)} />
              <Metric label={t("comm.m.samples")} value={String(metrics.audio_sample_count ?? 0)} />
              <Metric label={t("comm.m.fluency")} value={format(metrics.fluency_score)} icon={<Gauge className="h-3 w-3" />} />
              <Metric label={t("comm.m.nervousness")} value={format(metrics.nervousness_score)} />
              <Metric label={t("comm.m.confidence")} value={format(metrics.confidence_score)} />
              <Metric label={t("comm.m.pace")} value={metrics.avg_words_per_minute ? t("comm.m.paceFmt", { wpm: metrics.avg_words_per_minute }) : "-"} />
              <Metric label={t("comm.m.volume")} value={format(metrics.avg_volume)} icon={<Volume2 className="h-3 w-3" />} />
              <Metric label={t("comm.m.silence")} value={percent(metrics.silence_rate)} />
            </div>
          )}
        </Panel>
        <Panel icon={<Camera className="h-4 w-4 text-accent-emerald" />} title={t("comm.video")}>
          <p>{analysis.video || t("comm.noVideo")}</p>
          {video && (
            <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
              <Metric label={t("comm.m.sampleCount")} value={String(video.sample_count ?? 0)} />
              <Metric label={t("comm.m.attention")} value={format(video.avg_attention_score)} />
              <Metric label={t("comm.m.visualNerv")} value={format(video.visual_nervousness_score)} />
              <Metric label={t("comm.m.presence")} value={percent(video.presence_rate)} />
              <Metric label={t("comm.m.center")} value={percent(video.center_rate)} />
              <Metric label={t("comm.m.lighting")} value={video.lighting_quality || "-"} />
              <Metric label={t("comm.m.motion")} value={video.motion_quality || "-"} />
              <Metric label={t("comm.m.jitter")} value={format(video.avg_motion_proxy)} />
            </div>
          )}
        </Panel>
      </div>

      {(analysis.audio_dimensions?.length || analysis.video_dimensions?.length) && (
        <div className="grid gap-6 lg:grid-cols-2">
          <DimensionGroup title={t("comm.audioDim")} items={analysis.audio_dimensions || []} />
          <DimensionGroup title={t("comm.videoDim")} items={analysis.video_dimensions || []} />
        </div>
      )}
    </div>
  );
}

function DimensionGroup({ title, items }: { title: string; items: SignalDimension[] }) {
  const t = useT();
  if (!items.length) {
    return (
      <section className="glass rounded-2xl p-6">
        <h3 className="text-base font-medium">{title}</h3>
        <p className="mt-3 text-sm text-ink-muted">{t("comm.noSamples")}</p>
      </section>
    );
  }
  return (
    <section className="glass rounded-2xl p-6">
      <h3 className="text-base font-medium">{title}</h3>
      <div className="mt-4 grid gap-3">
        {items.map((item) => (
          <article key={item.name} className="rounded-2xl border border-border bg-surface p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-medium text-ink">{item.name}</div>
                <div className="mt-1 text-xs text-ink-dim">{item.level}</div>
              </div>
              <div className="font-mono text-2xl text-ink">{item.score ?? "--"}</div>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-ink/10">
              <div className="h-full rounded-full bg-gradient-to-r from-accent-violet to-accent-cyan" style={{ width: `${Math.max(4, Math.min(100, item.score ?? 0))}%` }} />
            </div>
            <p className="mt-3 text-sm leading-relaxed text-ink-muted">{item.insight}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function Panel({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="glass rounded-2xl p-6">
      <div className="mb-3 flex items-center gap-2">
        {icon}
        <h3 className="text-base font-medium">{title}</h3>
      </div>
      <div className="text-sm leading-relaxed text-ink-muted">{children}</div>
    </div>
  );
}

function Metric({ label, value, icon }: { label: string; value: string; icon?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-2">
      <div className="flex items-center gap-1 text-ink-dim">
        {icon}
        {label}
      </div>
      <div className="mt-1 font-mono text-sm text-ink">{value}</div>
    </div>
  );
}

function format(value?: number | null) {
  return value == null ? "-" : String(value);
}

function percent(value?: number | null) {
  return value == null ? "-" : `${Math.round(value * 100)}%`;
}
