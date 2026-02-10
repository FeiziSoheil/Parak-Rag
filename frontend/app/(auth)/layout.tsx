"use client";

import dynamic from "next/dynamic";

// import LetterGlitch from "@/components/LetterGlitch";
const Plasma = dynamic(() => import("@/components/Plasma"), { ssr: false });

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen relative overflow-hidden bg-black">
      <div className="absolute inset-0">
        {/* LetterGlitch – برای تست و مقایسه با Plasma کامنت شده
        <LetterGlitch
          glitchColors={[
            "#27272a",
            "#3f3f46",
            "#52525b",
            "#71717a",
            "#a1a1aa",
          ]}
          glitchSpeed={50}
          centerVignette={true}
          outerVignette={false}
          smooth={true}
        />
        */}
        <Plasma
          color="#a1a1aa"
          speed={0.6}
          direction="forward"
          scale={1.1}
          opacity={0.8}
          mouseInteractive={true}
        />
        <div
          className="absolute inset-0 bg-black/60 pointer-events-none"
          aria-hidden
        />
      </div>
      <div className="relative z-10 min-h-screen flex items-center justify-center p-6 pointer-events-none">
        <div className="pointer-events-auto">
          {children}
        </div>
      </div>
    </div>
  );
}
