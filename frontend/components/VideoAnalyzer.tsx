"use client";

import { Camera, CameraOff, Gauge } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { recordAnalytics } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";

interface Props {
  sessionId?: string;
  disabled?: boolean;
}

export function VideoAnalyzer({ sessionId, disabled }: Props) {
  const t = useT();
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const lastFrameRef = useRef<Uint8ClampedArray | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [statusKey, setStatusKey] = useState<string>("video.statusOff");
  const [attention, setAttention] = useState(0);
  const [lightingKey, setLightingKey] = useState<string>("video.lightingPending");
  const [motionKey, setMotionKey] = useState<string>("video.motionPending");

  useEffect(() => () => stop(), []);

  useEffect(() => {
    if (!enabled || disabled || !sessionId) return;
    sample(sessionId);
    const id = window.setInterval(() => sample(sessionId), 3500);
    return () => window.clearInterval(id);
  }, [enabled, disabled, sessionId]);

  async function start() {
    if (disabled || enabled) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 360, facingMode: "user" },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) videoRef.current.srcObject = stream;
      setEnabled(true);
      setStatusKey("video.statusAnalyzing");
    } catch (err: any) {
      toast.error(`${t("video.openFail")}${err?.message || ""}`);
    }
  }

  function stop() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    lastFrameRef.current = null;
    setEnabled(false);
    setStatusKey("video.statusOff");
    setAttention(0);
    setLightingKey("video.lightingPending");
    setMotionKey("video.motionPending");
  }

  async function sample(sid: string) {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.videoWidth === 0) return;

    const width = 180;
    const height = Math.max(1, Math.round((video.videoHeight / video.videoWidth) * width));
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return;
    ctx.drawImage(video, 0, 0, width, height);
    const image = ctx.getImageData(0, 0, width, height);
    const data = image.data;

    let total = 0;
    let diff = 0;
    const previous = lastFrameRef.current;
    for (let i = 0; i < data.length; i += 4) {
      const gray = (data[i] + data[i + 1] + data[i + 2]) / 3;
      total += gray;
      if (previous) {
        const oldGray = (previous[i] + previous[i + 1] + previous[i + 2]) / 3;
        diff += Math.abs(gray - oldGray);
      }
    }
    lastFrameRef.current = new Uint8ClampedArray(data);

    const pixels = data.length / 4;
    const brightness = total / pixels;
    const motionProxy = previous ? diff / pixels : 0;
    const lightingKey = labelLightingKey(brightness);
    const motionKey = labelMotionKey(motionProxy);

    const face = await detectFace(video, width, height);
    const presence = face.face_count !== undefined ? face.face_count > 0 : brightness > 25;
    const centered = face.centered ?? presence;
    const attentionScore = scoreAttention({ presence, centered, brightness, motionProxy });
    const visualNervousness = scoreVisualNervousness({ presence, centered, motionProxy, brightness });

    setAttention(attentionScore);
    setLightingKey(lightingKey);
    setMotionKey(motionKey);
    setStatusKey(presence ? (attentionScore >= 70 ? "video.statusSteady" : "video.statusAdjust") : "video.statusNotVisible");

    recordAnalytics(sid, "video", {
      ts: Date.now(),
      brightness: Math.round(brightness),
      motion_proxy: Math.round(motionProxy * 10) / 10,
      face_count: face.face_count,
      centered,
      presence,
      attention_score: attentionScore,
      visual_nervousness: visualNervousness,
      lighting_label: lightingKey,
      motion_label: motionKey,
      face_center_x: face.center_x,
      face_center_y: face.center_y,
      note: face.face_count === undefined ? "FaceDetector unavailable; using visual proxies" : "FaceDetector enabled",
    }).catch(() => undefined);
  }

  return (
    <div className="fixed bottom-20 left-4 z-[70] w-64 overflow-hidden rounded-2xl border border-border bg-background/85 shadow-2xl backdrop-blur lg:bottom-4 lg:left-[19rem]">
      <div className="relative aspect-video bg-black">
        <video ref={videoRef} autoPlay muted playsInline className={cn("h-full w-full object-cover", !enabled && "opacity-25")} />
        <canvas ref={canvasRef} className="hidden" />
        {!enabled && <div className="absolute inset-0 flex items-center justify-center text-xs text-white/65">{t("video.onMsg")}</div>}
        <div className="absolute right-2 top-2 rounded-full bg-black/60 px-2 py-1 text-[10px] text-white/75">{attention ? `${attention}` : "--"}</div>
      </div>
      <div className="space-y-2 px-3 py-2 text-xs text-ink-muted">
        <div className="flex items-center justify-between gap-2">
          <span className="truncate">{t(statusKey)}</span>
          <button
            type="button"
            onClick={enabled ? stop : start}
            disabled={disabled}
            className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-border text-ink-muted hover:text-ink disabled:opacity-40"
            title={enabled ? t("video.tip.off") : t("video.tip.on")}
          >
            {enabled ? <CameraOff className="h-4 w-4" /> : <Camera className="h-4 w-4" />}
          </button>
        </div>
        <div className="grid grid-cols-3 gap-1">
          <Badge labelKey="video.label.light" valueKey={lightingKey} />
          <Badge labelKey="video.label.motion" valueKey={motionKey} />
          <Badge labelKey="video.label.state" value={attention ? `${attention}` : "-"} icon />
        </div>
      </div>
    </div>
  );
}

async function detectFace(video: HTMLVideoElement, width: number, height: number): Promise<{ face_count?: number; centered?: boolean; center_x?: number; center_y?: number }> {
  const FaceDetector = (window as any).FaceDetector;
  if (!FaceDetector) return {};
  try {
    const detector = new FaceDetector({ fastMode: true, maxDetectedFaces: 2 });
    const faces = await detector.detect(video);
    const box = faces[0]?.boundingBox;
    if (!box) return { face_count: faces.length };
    const centerX = (box.x + box.width / 2) / (video.videoWidth || width);
    const centerY = (box.y + box.height / 2) / (video.videoHeight || height);
    return {
      face_count: faces.length,
      centered: centerX > 0.25 && centerX < 0.75 && centerY > 0.18 && centerY < 0.78,
      center_x: Math.round(centerX * 100) / 100,
      center_y: Math.round(centerY * 100) / 100,
    };
  } catch {
    return {};
  }
}

function scoreAttention({ presence, centered, brightness, motionProxy }: { presence: boolean; centered: boolean; brightness: number; motionProxy: number }) {
  let score = presence ? 62 : 25;
  if (centered) score += 14;
  if (brightness >= 45 && brightness <= 210) score += 14;
  if (motionProxy < 8) score += 10;
  else if (motionProxy < 22) score += 4;
  return Math.max(0, Math.min(100, Math.round(score)));
}

function scoreVisualNervousness({ presence, centered, motionProxy, brightness }: { presence: boolean; centered: boolean; motionProxy: number; brightness: number }) {
  let score = 18;
  if (!presence) score += 28;
  if (!centered) score += 14;
  score += Math.min(38, motionProxy * 1.5);
  if (brightness < 45 || brightness > 210) score += 8;
  return Math.max(0, Math.min(100, Math.round(score)));
}

function labelLightingKey(brightness: number): string {
  if (brightness < 45) return "video.lightingDim";
  if (brightness > 210) return "video.lightingBright";
  return "video.lightingFit";
}

function labelMotionKey(value: number): string {
  if (value < 8) return "video.motionSteady";
  if (value < 22) return "video.motionMild";
  return "video.motionLarge";
}

function Badge({ labelKey, valueKey, value, icon }: { labelKey: string; valueKey?: string; value?: string; icon?: boolean }) {
  const t = useT();
  return (
    <div className="rounded-xl border border-border bg-surface px-2 py-1">
      <div className="flex items-center gap-1 text-[10px] text-ink-dim">
        {icon && <Gauge className="h-3 w-3" />}
        {t(labelKey)}
      </div>
      <div className="mt-0.5 truncate text-ink">{valueKey ? t(valueKey) : value}</div>
    </div>
  );
}
