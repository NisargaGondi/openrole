import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { DailySignalBar } from "@/components/signal/DailySignalBar";
import { SignalBackground } from "@/components/signal/SignalBackground";
import { ThemeProvider } from "@/components/signal/ThemeProvider";
import { PipelineRunProvider } from "@/components/signal/PipelineRunProvider";
import { TopNav } from "@/components/signal/TopNav";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "OpenRole — Signal",
  description: "Job hunt mission control: scout, network, outreach, apply",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full`} suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem("openrole_theme");var d=t==="dark"||(!t&&window.matchMedia("(prefers-color-scheme: dark)").matches);if(d)document.documentElement.classList.add("dark");}catch(e){}})();`,
          }}
        />
      </head>
      <body className="min-h-full font-sans antialiased text-slate-900 dark:text-slate-100">
        <ThemeProvider>
          <PipelineRunProvider>
            <SignalBackground />
            <TopNav />
            <main className="mx-auto max-w-[1480px] px-4 pb-24 pt-2 md:px-6">{children}</main>
            <DailySignalBar />
          </PipelineRunProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
