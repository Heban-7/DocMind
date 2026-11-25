"use client";

import { useState } from "react";
import Navbar from "@/components/layout/Navbar";
import Footer from "@/components/layout/Footer";

export default function ContactPage() {
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const copyToClipboard = (val: string, label: string) => {
    navigator.clipboard.writeText(val);
    setToastMessage(`Copied ${label} to clipboard!`);
    setTimeout(() => setToastMessage(null), 3000);
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-[#03050f] text-slate-900 dark:text-white transition-colors">
      <Navbar />

      {/* Main Content Canvas */}
      <main className="pt-28 px-gutter pb-xl min-h-screen flex flex-col items-center">
        {/* Toast Notification */}
        {toastMessage && (
          <div className="fixed bottom-6 right-6 z-50 bg-primary text-white px-md py-sm rounded-xl shadow-lg font-label-md text-xs font-bold flex items-center gap-xs fade-in">
            <span className="material-symbols-outlined text-[18px]">done</span>
            <span>{toastMessage}</span>
          </div>
        )}

        {/* Headline */}
        <div className="w-full max-w-[800px] mb-xl text-center md:text-left">
          <h1 className="font-display text-3xl md:text-4xl font-bold text-slate-900 dark:text-white mb-xs">
            Let&apos;s connect.
          </h1>
          <p className="font-body-md text-sm text-slate-600 dark:text-slate-400">
            Questions about how DocMind works, a bug, or an idea? Open an issue on GitHub, or write to me directly.
          </p>
        </div>

        {/* Contact Layout */}
        <div className="w-full max-w-[800px] grid grid-cols-1 lg:grid-cols-12 gap-xl items-start">
          {/* GitHub issues: the one channel that is tracked in the open */}
          <div className="lg:col-span-8 bg-white dark:bg-[#0c1021] border border-slate-200 dark:border-slate-800 rounded-2xl p-xl shadow-md space-y-md">
            <h2 className="font-bold text-lg">Report a problem or ask a question</h2>
            <p className="text-sm text-slate-600 dark:text-slate-400">
              Issues on GitHub are public and searchable, so an answer helps the next person too. Please include the
              document type, what you asked, and what you expected; leave out anything confidential.
            </p>
            <div className="flex flex-wrap gap-sm">
              <a
                href="https://github.com/Heban-7/DocMind/issues/new"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-xs bg-primary text-white px-4 py-2 rounded-xl text-sm font-bold hover:opacity-90"
              >
                <span className="material-symbols-outlined text-[18px]" aria-hidden="true">bug_report</span>
                Open an issue
              </a>
              <a
                href="https://github.com/Heban-7/DocMind/issues"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-xs border border-slate-300 dark:border-slate-700 px-4 py-2 rounded-xl text-sm hover:border-primary"
              >
                See open issues
              </a>
            </div>
          </div>

          {/* Side Info */}
          <div className="lg:col-span-4 space-y-lg">
            <div className="bg-white dark:bg-[#0c1021] border border-slate-200 dark:border-slate-800 rounded-2xl p-lg shadow-md">
              <h3 className="font-label-md text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest mb-md">
                Direct Channels
              </h3>
              <div className="flex flex-col gap-sm">
                <button
                  onClick={() => copyToClipboard("liuljima1896@gmail.com", "email address")}
                  className="flex items-center justify-between p-md rounded-xl bg-slate-50 dark:bg-slate-900/60 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-800 transition-all text-left group"
                >
                  <div className="flex items-center gap-sm">
                    <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                      <span className="material-symbols-outlined text-[18px]">mail</span>
                    </div>
                    <div>
                      <span className="font-label-md text-xs font-bold block text-slate-900 dark:text-white">Email</span>
                      <span className="font-body-sm text-[11px] text-slate-600 dark:text-slate-400 truncate block max-w-[140px]">
                        liuljima1896@gmail.com
                      </span>
                    </div>
                  </div>
                </button>

                <a
                  href="https://www.linkedin.com/in/liul-j-teshome"
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center justify-between p-md rounded-xl bg-slate-50 dark:bg-slate-900/60 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-800 transition-all text-left group"
                >
                  <div className="flex items-center gap-sm">
                    <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                      <span className="material-symbols-outlined text-[18px]">link</span>
                    </div>
                    <div>
                      <span className="font-label-md text-xs font-bold block text-slate-900 dark:text-white">LinkedIn</span>
                      <span className="font-body-sm text-[11px] text-slate-600 dark:text-slate-400 block">
                        liul-j-teshome
                      </span>
                    </div>
                  </div>
                  <span className="material-symbols-outlined text-xs text-slate-400 group-hover:text-primary">
                    open_in_new
                  </span>
                </a>

                <a
                  href="https://x.com/linnet_ai"
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center justify-between p-md rounded-xl bg-slate-50 dark:bg-slate-900/60 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-800 transition-all text-left group"
                >
                  <div className="flex items-center gap-sm">
                    <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                      <span className="material-symbols-outlined text-[18px]">brand_awareness</span>
                    </div>
                    <div>
                      <span className="font-label-md text-xs font-bold block text-slate-900 dark:text-white">Twitter / X</span>
                      <span className="font-body-sm text-[11px] text-slate-600 dark:text-slate-400 block">
                        @linnet_ai
                      </span>
                    </div>
                  </div>
                  <span className="material-symbols-outlined text-xs text-slate-400 group-hover:text-primary">
                    open_in_new
                  </span>
                </a>
              </div>
            </div>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
