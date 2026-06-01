"use client";

import Image from "next/image";
import Link from "next/link";

interface Props {
  compact?: boolean;
  href?: string;
}

export function BrandMark({ compact, href = "/" }: Props) {
  return (
    <Link href={href} className="inline-flex min-w-0 items-center gap-3">
      <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-border bg-white/95 p-1.5 shadow-glow">
        <Image src="/ecnu-logo.svg" width={34} height={34} alt="华东师范大学" className="h-full w-full object-contain" priority />
      </span>
      {!compact && (
        <span className="min-w-0">
          <span className="block truncate text-sm font-medium tracking-wide text-ink">华东师范大学 · Aurora</span>
          <span className="block truncate text-xs text-ink-dim">AI Interview System</span>
        </span>
      )}
    </Link>
  );
}
