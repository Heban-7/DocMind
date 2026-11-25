"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/context/AuthContext";

export const APP_LINKS = [
  { href: "/dashboard", label: "Chat", icon: "chat" },
  { href: "/review", label: "Review", icon: "fact_check" },
  { href: "/usage", label: "Usage", icon: "payments" },
  { href: "/benchmarks", label: "Benchmarks", icon: "monitoring" },
];

/** The frame of the signed-in pages other than the chat: a top bar and the page. */
export default function AppShell({ title, actions, children }: { title: string; actions?: React.ReactNode; children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { isAuthenticated, isLoading, logout } = useAuth();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) router.replace("/login");
  }, [isLoading, isAuthenticated, router]);

  if (isLoading || !isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-[#03050f] text-slate-500" role="status">
        <span className="material-symbols-outlined animate-spin mr-2" aria-hidden="true">progress_activity</span>
        Checking your sign-in…
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-[#03050f] text-slate-900 dark:text-white">
      <header className="sticky top-0 z-30 bg-white/90 dark:bg-[#0c1021]/90 backdrop-blur border-b border-slate-200 dark:border-slate-800">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center gap-4">
          <Link href="/dashboard" className="flex items-center gap-2 shrink-0" aria-label="DocMind, back to the chat">
            <Image src="/logo.jpg" alt="" width={28} height={28} className="w-7 h-7 rounded-md object-cover" />
            <span className="font-bold hidden sm:inline">DocMind</span>
          </Link>
          <nav aria-label="Main" className="flex items-center gap-1 overflow-x-auto">
            {APP_LINKS.map((l) => {
              const active = pathname === l.href || (l.href !== "/dashboard" && pathname.startsWith(l.href));
              return (
                <Link
                  key={l.href}
                  href={l.href}
                  aria-current={active ? "page" : undefined}
                  className={`flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm whitespace-nowrap ${
                    active ? "bg-primary/10 text-primary font-bold" : "text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
                  }`}
                >
                  <span className="material-symbols-outlined text-[18px]" aria-hidden="true">{l.icon}</span>
                  {l.label}
                </Link>
              );
            })}
          </nav>
          <button
            type="button"
            onClick={logout}
            aria-label="Sign out"
            className="ml-auto text-sm text-slate-500 hover:text-red-600 flex items-center gap-1 shrink-0"
          >
            <span className="material-symbols-outlined text-[18px]" aria-hidden="true">logout</span>
            <span className="hidden sm:inline">Sign out</span>
          </button>
        </div>
      </header>
      <main className="max-w-7xl mx-auto px-4 py-6">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
          <h1 className="text-2xl font-bold">{title}</h1>
          {actions}
        </div>
        {children}
      </main>
    </div>
  );
}

export function Card({ title, children, className = "" }: { title?: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={`bg-white dark:bg-[#0c1021] border border-slate-200 dark:border-slate-800 rounded-2xl p-4 ${className}`}>
      {title && <h2 className="text-sm font-bold text-slate-700 dark:text-slate-200 mb-3">{title}</h2>}
      {children}
    </section>
  );
}

export function ErrorNote({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="mb-4 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-700 dark:text-red-300">
      {message}
    </p>
  );
}
