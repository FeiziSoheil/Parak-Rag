import type { Metadata } from "next";
import localFont from "next/font/local";
import { DirectionProvider } from "@/components/DirectionProvider";
import { Toaster } from "@/components/ui/sonner";
import { ThemeProvider } from "next-themes";
import { AccentThemeProvider } from "@/contexts/AccentThemeContext";
import "./globals.css";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: "PARAK - Intelligent Assistant",
  description: "PARAK (پَرَک) — یک دستیار هوشمند با قابلیت گفتگو و جستجوی هوشمند محصولات. Intelligent conversational assistant with RAG.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="scroll-smooth" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} font-sans antialiased min-h-screen bg-background text-foreground`}
      >
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
          <AccentThemeProvider>
            <DirectionProvider>
              {children}
              <Toaster position="bottom-right" richColors />
            </DirectionProvider>
          </AccentThemeProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
