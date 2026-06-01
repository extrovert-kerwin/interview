"use client";

import { Mic, Square } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { recordAnalytics } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export interface SpeechMetrics {
  source: "browser_asr";
  duration_ms: number;
  confidence?: number;
  transcript_length: number;
  interim_updates?: number;
  final_segments?: number;
  avg_volume?: number;
  peak_volume?: number;
  silence_rate?: number;
  volume_stability?: number;
  volume_variability?: number;
}

export interface VoiceClip {
  url: string;
  mimeType: string;
  durationMs: number;
}

interface Props {
  sessionId?: string;
  disabled?: boolean;
  onTranscript: (text: string, metrics: SpeechMetrics, clip?: VoiceClip) => void;
}

export function VoiceRecorder({ sessionId, disabled, onTranscript }: Props) {
  const t = useT();
  const [recording, setRecording] = useState(false);
  const recRef = useRef<any>(null);
  const startedAtRef = useRef(0);
  const finalTextRef = useRef("");
  const confidenceRef = useRef<number | undefined>();
  const interimUpdatesRef = useRef(0);
  const finalSegmentsRef = useRef(0);
  const audioRef = useRef<AudioRuntime | null>(null);

  async function start() {
    if (disabled || recording) return;
    const Rec: any = (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition;
    if (!Rec) {
      toast.error(t("voice.unsupported"));
      return;
    }

    finalTextRef.current = "";
    confidenceRef.current = undefined;
    interimUpdatesRef.current = 0;
    finalSegmentsRef.current = 0;
    startedAtRef.current = Date.now();
    audioRef.current = await startAudioRuntime(sessionId);

    const rec = new Rec();
    rec.lang = "zh-CN";
    rec.continuous = true;
    rec.interimResults = true;

    rec.onresult = (e: any) => {
      let finalText = "";
      let confidenceTotal = 0;
      let confidenceCount = 0;
      let finalSegments = 0;
      let interimUpdates = 0;
      for (let i = 0; i < e.results.length; i += 1) {
        const result = e.results[i];
        const alt = result?.[0];
        if (result.isFinal && alt?.transcript) {
          finalText += alt.transcript;
          finalSegments += 1;
          if (typeof alt.confidence === "number" && alt.confidence > 0) {
            confidenceTotal += alt.confidence;
            confidenceCount += 1;
          }
        } else if (alt?.transcript) {
          interimUpdates += 1;
        }
      }
      if (finalText) finalTextRef.current = finalText.trim();
      finalSegmentsRef.current = Math.max(finalSegmentsRef.current, finalSegments);
      interimUpdatesRef.current += interimUpdates;
      if (confidenceCount > 0) confidenceRef.current = confidenceTotal / confidenceCount;
    };

    rec.onerror = async () => {
      toast.error(t("voice.recognizeFail"));
      await cleanupAudio();
      setRecording(false);
    };
    rec.onend = async () => {
      setRecording(false);
      const text = finalTextRef.current.trim();
      const finished = await finishAudioRuntime(audioRef.current);
      audioRef.current = null;
      if (!text) return;
      const durationMs = Date.now() - startedAtRef.current;
      onTranscript(
        text,
        {
          source: "browser_asr",
          duration_ms: durationMs,
          confidence: confidenceRef.current,
          transcript_length: text.length,
          interim_updates: interimUpdatesRef.current,
          final_segments: finalSegmentsRef.current,
          ...finished.metrics,
        },
        finished.clip ? { ...finished.clip, durationMs } : undefined,
      );
      toast.success(t("voice.transcribed"));
    };

    recRef.current = rec;
    rec.start();
    setRecording(true);
  }

  function stop() {
    recRef.current?.stop();
  }

  async function cleanupAudio() {
    await finishAudioRuntime(audioRef.current);
    audioRef.current = null;
  }

  return (
    <button
      type="button"
      onClick={recording ? stop : start}
      disabled={disabled}
      className={cn(
        "inline-flex h-10 w-10 items-center justify-center rounded-full border transition",
        recording ? "border-accent-rose/60 bg-accent-rose/15 text-accent-rose shadow-glow" : "border-border bg-surface text-ink-muted hover:text-ink",
        disabled && "opacity-50",
      )}
      title={recording ? t("voice.stop") : t("voice.start")}
    >
      {recording ? <Square className="h-4 w-4 fill-current" /> : <Mic className="h-4 w-4" />}
    </button>
  );
}

interface AudioRuntime {
  stream: MediaStream;
  context: AudioContext;
  analyser: AnalyserNode;
  data: Uint8Array;
  timer: number;
  samples: number[];
  silenceWindows: number;
  recorder?: MediaRecorder;
  chunks: BlobPart[];
  mimeType: string;
}

async function startAudioRuntime(sessionId?: string): Promise<AudioRuntime | null> {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    const context = new AudioContext();
    const source = context.createMediaStreamSource(stream);
    const analyser = context.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);
    const mimeType = pickAudioMimeType();
    const runtime: AudioRuntime = { stream, context, analyser, data: new Uint8Array(analyser.fftSize), timer: 0, samples: [], silenceWindows: 0, chunks: [], mimeType };
    if (typeof MediaRecorder !== "undefined") {
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) runtime.chunks.push(event.data);
      };
      recorder.start();
      runtime.recorder = recorder;
    }
    runtime.timer = window.setInterval(() => sampleAudio(runtime, sessionId), 1200);
    return runtime;
  } catch {
    return null;
  }
}

function sampleAudio(runtime: AudioRuntime, sessionId?: string) {
  runtime.analyser.getByteTimeDomainData(runtime.data);
  let sum = 0;
  let peak = 0;
  for (const value of runtime.data) {
    const normalized = Math.abs((value - 128) / 128);
    sum += normalized * normalized;
    peak = Math.max(peak, normalized);
  }
  const rms = Math.sqrt(sum / runtime.data.length);
  runtime.samples.push(rms);
  if (rms < 0.015) runtime.silenceWindows += 1;
  const summary = summarizeSamples(runtime.samples, runtime.silenceWindows);
  if (sessionId) {
    recordAnalytics(sessionId, "audio", {
      ts: Date.now(),
      avg_volume: summary.avg_volume,
      peak_volume: Math.round(peak * 1000) / 1000,
      silence_rate: summary.silence_rate,
      volume_stability: summary.volume_stability,
      volume_variability: summary.volume_variability,
    }).catch(() => undefined);
  }
}

async function finishAudioRuntime(runtime: AudioRuntime | null): Promise<{ metrics: Partial<SpeechMetrics>; clip?: VoiceClip }> {
  if (!runtime) return { metrics: {} };
  window.clearInterval(runtime.timer);
  if (runtime.samples.length === 0) sampleAudio(runtime);
  const metrics = summarizeSamples(runtime.samples, runtime.silenceWindows);
  const clip = await stopRecorder(runtime);
  runtime.stream.getTracks().forEach((track) => track.stop());
  runtime.context.close().catch(() => undefined);
  return { metrics, clip };
}

function stopRecorder(runtime: AudioRuntime): Promise<VoiceClip | undefined> {
  const recorder = runtime.recorder;
  if (!recorder || recorder.state === "inactive") {
    return Promise.resolve(makeClip(runtime));
  }
  return new Promise((resolve) => {
    recorder.onstop = () => resolve(makeClip(runtime));
    recorder.stop();
  });
}

function makeClip(runtime: AudioRuntime): VoiceClip | undefined {
  if (!runtime.chunks.length) return undefined;
  const blob = new Blob(runtime.chunks, { type: runtime.mimeType || "audio/webm" });
  return { url: URL.createObjectURL(blob), mimeType: blob.type || "audio/webm", durationMs: 0 };
}

function summarizeSamples(samples: number[], silenceWindows: number): Partial<SpeechMetrics> {
  if (!samples.length) return {};
  const avg = samples.reduce((sum, value) => sum + value, 0) / samples.length;
  const variance = samples.reduce((sum, value) => sum + Math.pow(value - avg, 2), 0) / samples.length;
  const variability = Math.sqrt(variance);
  const stability = 1 - Math.min(1, variability / Math.max(avg, 0.01));
  return {
    avg_volume: Math.round(avg * 1000) / 1000,
    peak_volume: Math.round(Math.max(...samples) * 1000) / 1000,
    silence_rate: Math.round((silenceWindows / samples.length) * 100) / 100,
    volume_stability: Math.round(stability * 100) / 100,
    volume_variability: Math.round(variability * 1000) / 1000,
  };
}

function pickAudioMimeType() {
  if (typeof MediaRecorder === "undefined") return "";
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
  return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || "";
}
