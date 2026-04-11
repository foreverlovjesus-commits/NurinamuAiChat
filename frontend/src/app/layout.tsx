import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "누리나무 AI 법률통합지원 시스템 | 국민권익위원회",
  description:
    "행동강령, 청탁금지법, 공익신고 보호 등 최신 법규를 AI로 검색하고 안전한 답변을 제공하는 국민권익위원회 공식 AI 지원 시스템입니다.",
  keywords: "청탁금지법, 행동강령, 공익신고, 국민권익위원회, 법령검색, AI",
  authors: [{ name: "국민권익위원회" }],
  robots: "noindex, nofollow", // 공공 내부 시스템 — 검색 엔진 차단
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="ko"
      className="h-full antialiased"
    >
      <head>
        {/* Pretendard — 공공기관 표준 웹폰트 */}
        <link
          rel="stylesheet"
          as="style"
          crossOrigin="anonymous"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css"
        />
      </head>
      <body className="min-h-full flex flex-col">
        {/* 웹 접근성 (KWCAG 2.1): 스킵 내비게이션 */}
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[9999] focus:px-4 focus:py-2 focus:bg-gov-navy focus:text-white focus:rounded-md focus:font-bold focus:text-sm"
        >
          본문 바로가기
        </a>
        <main id="main-content" className="flex-1 flex flex-col">
          {children}
        </main>
      </body>
    </html>
  );
}
