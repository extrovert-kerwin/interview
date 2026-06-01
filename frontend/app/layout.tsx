import type { Metadata } from "next";
import { Toaster } from "sonner";

import { AppShell } from "@/components/AppShell";
import { BackgroundAurora } from "@/components/BackgroundAurora";
import { I18nProvider } from "@/lib/i18n";
import "./globals.css";

export const metadata: Metadata = {
  title: "Aurora · AI Interview System",
  description: "Upload your resume, run an AI interview, get a visual evaluation report.",
};

// Inline script runs synchronously before first paint to prevent theme/locale flash.
const bootScript = `
(function(){
  try {
    var t = localStorage.getItem('aurora_theme');
    var cls = (t === 'light') ? 'light' : 'dark';
    document.documentElement.classList.add(cls);
    if (cls === 'light') document.documentElement.classList.remove('dark');
  } catch(e) {
    document.documentElement.classList.add('dark');
  }
  try {
    var saved = localStorage.getItem('aurora_locale');
    var loc = (saved === 'zh' || saved === 'en')
      ? saved
      : ((navigator.language || '').toLowerCase().indexOf('en') === 0 ? 'en' : 'zh');
    document.documentElement.setAttribute('lang', loc === 'zh' ? 'zh-CN' : 'en');
  } catch(e) {
    document.documentElement.setAttribute('lang', 'zh-CN');
  }
})();
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className="dark">
      <head>
        {/* eslint-disable-next-line @next/next/no-sync-scripts */}
        <script dangerouslySetInnerHTML={{ __html: bootScript }} />
      </head>
      <body className="relative min-h-screen overflow-x-hidden antialiased">
        <I18nProvider>
          <BackgroundAurora />
          <AppShell>{children}</AppShell>
          {/* Toaster theme is set via data attribute — AppShell syncs it */}
          <Toaster
            richColors
            position="top-center"
            theme="system"
          />
        </I18nProvider>
      </body>
    </html>
  );
}
