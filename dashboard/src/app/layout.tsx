/**
 * Root shell: sidebar + header + provenance bar.
 *
 * Every observability route renders inside this. Two things are set here on purpose:
 *
 *   - Pretendard is loaded as a local variable font exposed through
 *     `--font-pretendard`, which is the variable the generated tokens reference.
 *     If the package, this loader, or the variable name drift apart the page does
 *     *not* break — the CSS font stack silently falls back to the system font and
 *     the failure is invisible. It has to be checked by eye.
 *   - `adjustFontFallback: false` because Next's metric-adjusted fallback shifts the
 *     layout between fallback and Pretendard, and a dashboard whose job is comparing
 *     numbers must not move under the reader (CLS).
 */
import type { Metadata } from "next";
import Image from "next/image";
import localFont from "next/font/local";

import "./globals.css";
import { Sidebar } from "@/components/Sidebar";

const pretendard = localFont({
  src: "../../node_modules/pretendard/dist/web/variable/woff2/PretendardVariable.woff2",
  variable: "--font-pretendard",
  weight: "100 900",
  display: "swap",
  adjustFontFallback: false,
});

export const metadata: Metadata = {
  title: { default: "관측 대시보드", template: "%s | 관측 대시보드" },
  description:
    "측정 계층이 게시한 산출물을 읽어 수집 현황·계약 위반·충족률·KPI·데이터 품질·봉인 상태를 표시한다.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko" className={`${pretendard.variable} h-full`}>
      <body className="min-h-full">
        {/* Keyboard users reach the content without walking the whole sidebar.
            Visible only on focus, never hidden from the accessibility tree. */}
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-base focus:top-base focus:z-header focus:rounded-md focus:bg-surface focus:px-base focus:py-sm focus:text-label-md"
        >
          본문으로 건너뛰기
        </a>
        <div className="flex min-h-full">
          <Sidebar />
          <div className="min-w-0 flex-1">
            <main id="main" className="mx-auto max-w-(--container-dashboard-max) px-base py-lg lg:px-page-gutter">
              {children}
            </main>
            {/* Team logo slot. Swap public/brand/team-logo.svg for the Figma export. */}
            <footer className="mx-auto flex max-w-(--container-dashboard-max) items-center gap-sm border-t border-border px-base py-md lg:px-page-gutter">
              <Image src="/brand/team-logo.svg" alt="팀 로고" width={120} height={24} unoptimized className="h-6 w-auto" />
              <span className="text-caption text-text-secondary">72offsuit · AI 리텐션 ROI</span>
            </footer>
          </div>
        </div>
      </body>
    </html>
  );
}
