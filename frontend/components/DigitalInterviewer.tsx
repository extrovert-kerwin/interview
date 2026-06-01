"use client";

import Image from "next/image";
import { RotateCcw, Volume2, VolumeX, Waves } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";

interface Props {
  text?: string;
  disabled?: boolean;
}

const AVATAR_SRC = "/images/female-digital-interviewer.png";

export function DigitalInterviewer({ text, disabled }: Props) {
  const t = useT();
  const [muted, setMuted] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [voiceName, setVoiceName] = useState("");
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const display = useMemo(() => (text || "").replace(/^提示[:：]\s*/, "").trim(), [text]);

  useEffect(() => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    const loadVoices = () => {
      const all = window.speechSynthesis.getVoices();
      const zhVoices = all.filter((voice) => voice.lang.toLowerCase().startsWith("zh"));
      const femalePreferred =
        zhVoices.find((voice) => /xiaoxiao|xiaoyi|xiaobei|tingting|huihui|female|woman/i.test(voice.name)) ||
        zhVoices.find((voice) => /mandarin|chinese|yunxi/i.test(voice.name)) ||
        zhVoices[0] ||
        all[0];
      setVoices(zhVoices.length ? zhVoices : all);
      setVoiceName((current) => current || femalePreferred?.name || "");
    };
    loadVoices();
    window.speechSynthesis.onvoiceschanged = loadVoices;
    return () => {
      window.speechSynthesis.onvoiceschanged = null;
    };
  }, []);

  useEffect(() => {
    if (disabled || muted || !display) return;
    speak(display);
    return () => {
      window.speechSynthesis?.cancel();
      setSpeaking(false);
    };
  }, [display, disabled, muted, voiceName]);

  function speak(content: string) {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(content);
    utter.lang = "zh-CN";
    utter.rate = 1.26;
    utter.pitch = 1.08;
    utter.volume = 1;
    const selected = voices.find((voice) => voice.name === voiceName);
    if (selected) utter.voice = selected;
    utter.onstart = () => setSpeaking(true);
    utter.onend = () => setSpeaking(false);
    utter.onerror = () => setSpeaking(false);
    window.speechSynthesis.speak(utter);
  }

  return (
    <div className="glass mb-4 flex items-center gap-4 rounded-2xl p-4">
      <div className="relative flex h-28 w-28 shrink-0 items-center justify-center">
        <div
          className={cn(
            "absolute inset-0 rounded-full bg-gradient-to-br from-rose-400/35 via-accent-violet/25 to-accent-cyan/30 opacity-60 blur-xl transition",
            speaking && "scale-110 opacity-100",
          )}
        />
        <div className="relative h-24 w-24 overflow-hidden rounded-full border border-border bg-surface shadow-glow">
          <Image src={AVATAR_SRC} alt={t("digital.alt")} fill priority sizes="96px" className="object-cover" />
          <div className="absolute inset-x-0 bottom-0 h-1/3 bg-gradient-to-t from-black/45 to-transparent" />
          <div
            className={cn(
              "absolute left-1/2 top-[61%] h-1.5 w-5 -translate-x-1/2 rounded-full bg-rose-950/75 opacity-70 shadow-[0_0_10px_rgba(244,114,182,0.45)] transition",
              speaking && "h-2.5 w-6 animate-pulse opacity-95",
            )}
          />
          {speaking && (
            <div className="absolute inset-x-4 bottom-3 flex items-end justify-center gap-1">
              {[8, 13, 18, 12, 9].map((height, index) => (
                <span
                  key={index}
                  className="w-1 rounded-full bg-accent-cyan/80 shadow-[0_0_10px_rgba(34,211,238,0.7)]"
                  style={{ height, animation: `pulse 0.55s ${index * 0.08}s infinite alternate` }}
                />
              ))}
            </div>
          )}
        </div>
        {speaking && <span className="absolute inset-0 animate-ping rounded-full border border-accent-cyan/40" />}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-dim">
          <Waves className={cn("h-3.5 w-3.5", speaking && "text-accent-cyan")} />
          {t("digital.label")}
        </div>
        <div className="mt-1 text-sm text-ink-muted">
          {speaking ? t("digital.speaking") : muted ? t("digital.muted") : t("digital.idle")}
        </div>
        {voices.length > 1 && (
          <select
            value={voiceName}
            onChange={(e) => setVoiceName(e.target.value)}
            className="mt-2 max-w-full rounded-full border border-border bg-surface px-3 py-1 text-xs text-ink-muted outline-none"
            aria-label={t("digital.voicePick")}
          >
            {voices.map((voice) => (
              <option key={voice.name} value={voice.name}>
                {voice.name}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => display && speak(display)}
          disabled={disabled || muted || !display}
          className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-border text-ink-muted transition hover:border-ink/30 hover:text-ink disabled:opacity-40"
          title={t("digital.replay")}
        >
          <RotateCcw className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={() => {
            window.speechSynthesis?.cancel();
            setSpeaking(false);
            setMuted((v) => !v);
          }}
          className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-border text-ink-muted transition hover:border-ink/30 hover:text-ink"
          title={muted ? t("digital.muteOff") : t("digital.muteOn")}
        >
          {muted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
        </button>
      </div>
    </div>
  );
}
