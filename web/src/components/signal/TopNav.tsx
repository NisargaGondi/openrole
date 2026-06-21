"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  BarChart3,
  BookOpen,
  Home,
  Moon,
  Network,
  Radar,
  Radio,
  Search,
  Settings,
  Sun,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTheme } from "@/components/signal/ThemeProvider";
import { NotificationsPanel } from "@/components/signal/NotificationsPanel";
import { SearchPalette } from "@/components/signal/SearchPalette";

const NAV = [
  { href: "/", label: "Home", icon: Home },
  { href: "/scout", label: "Scout", icon: Radar },
  { href: "/library", label: "Library", icon: BookOpen },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/network", label: "Network", icon: Network },
  { href: "/", label: "Signals", icon: Zap, badge: "Beta", title: "Live mission control — network graph, pipeline, activity" },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function TopNav() {
  const path = usePathname();
  const { theme, toggle, ready } = useTheme();
  const [searchOpen, setSearchOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <>
      <SearchPalette open={searchOpen} onClose={() => setSearchOpen(false)} />
      <div className="sticky top-0 z-50 px-4 pt-3 md:px-6">
        <header className="glass-float mx-auto flex max-w-[1480px] items-center justify-between gap-2 rounded-2xl px-3 py-2 md:gap-3 md:px-5 md:py-2.5">
          <Link href="/" className="flex shrink-0 items-center gap-2.5">
            <span className="relative flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-md shadow-indigo-500/30">
              <Radio className="h-5 w-5" />
            </span>
            <span className="hidden text-lg font-extrabold tracking-tight signal-gradient-text sm:inline">OpenRole</span>
          </Link>

          <nav className="hidden items-center gap-0.5 xl:flex">
            {NAV.map(({ href, label, icon: Icon, badge, title }) => {
              const isActive = label === "Signals" ? path === "/" : path === href;
              return (
                <Link
                  key={label}
                  href={href}
                  title={title}
                  className={cn(
                    "relative flex items-center gap-1.5 rounded-full px-3 py-2 text-sm font-semibold transition",
                    isActive
                      ? "bg-indigo-100 text-indigo-700 shadow-sm dark:bg-indigo-900/60 dark:text-indigo-200"
                      : "text-slate-500 hover:bg-indigo-50 hover:text-indigo-600 dark:hover:bg-slate-800",
                  )}
                >
                  <Icon className="h-3.5 w-3.5 opacity-70" />
                  {label}
                  {badge && (
                    <span className="ml-0.5 rounded-full bg-violet-100 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-violet-600 dark:bg-violet-900 dark:text-violet-300">
                      {badge}
                    </span>
                  )}
                </Link>
              );
            })}
          </nav>

          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setSearchOpen(true)}
              className="rounded-full p-2 text-slate-400 transition hover:bg-indigo-50 hover:text-indigo-600 dark:hover:bg-slate-800"
              aria-label="Quick find role"
              title="Quick find saved role (⌘K)"
            >
              <Search className="h-5 w-5" />
            </button>
            <button
              type="button"
              onClick={toggle}
              className="hidden rounded-full p-2 text-slate-400 transition hover:bg-indigo-50 hover:text-indigo-600 dark:hover:bg-slate-800 sm:block"
              aria-label="Toggle theme"
            >
              {ready ? (theme === "dark" ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />) : <Moon className="h-5 w-5" />}
            </button>
            <NotificationsPanel />
            <div className="relative ml-1 flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-orange-400 text-xs font-bold text-white ring-2 ring-white dark:ring-slate-800">
              NG
            </div>
          </div>
        </header>

        <nav className="mx-auto mt-2 flex max-w-[1480px] gap-1 overflow-x-auto pb-1 xl:hidden">
          {NAV.map(({ href, label }) => (
            <Link
              key={label}
              href={href}
              className={cn(
                "shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold",
                (label === "Signals" ? path === "/" : path === href)
                  ? "bg-indigo-100 text-indigo-700"
                  : "text-slate-500",
              )}
            >
              {label}
            </Link>
          ))}
        </nav>
      </div>
    </>
  );
}
