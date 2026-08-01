"use client";

import { useState } from "react";
import Navbar from "@/components/layout/Navbar";
import Footer from "@/components/layout/Footer";

const topics = [
  "General Inquiry",
  "Enterprise Pilot",
  "Custom PDF Parser",
  "Zero-Trust Provenance",
];

export default function ContactPage() {
  const [selectedTopic, setSelectedTopic] = useState("Enterprise Pilot");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [formStatus, setFormStatus] = useState<"idle" | "sending" | "sent">("idle");
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !email || !message) return;
    setFormStatus("sending");
    setTimeout(() => {
      setFormStatus("sent");
      setToastMessage("Inquiry sent successfully! We will follow up shortly.");
      setName("");
      setEmail("");
      setMessage("");
      setTimeout(() => setToastMessage(null), 4000);
    }, 800);
  };

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
            Have questions about DocMind Refinery architecture or enterprise integration? Send a direct message below.
          </p>
        </div>

        {/* Contact Layout */}
        <div className="w-full max-w-[800px] grid grid-cols-1 lg:grid-cols-12 gap-xl items-start">
          {/* Form */}
          <div className="lg:col-span-8 bg-white dark:bg-[#0c1021] border border-slate-200 dark:border-slate-800 rounded-2xl p-xl shadow-md">
            {/* Topic Chips */}
            <div className="mb-lg">
              <label className="block font-label-md text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-sm">
                Topic of Interest
              </label>
              <div className="flex flex-wrap gap-xs">
                {topics.map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setSelectedTopic(t)}
                    className={`px-md py-1.5 rounded-lg text-xs font-label-md transition-all border ${
                      selectedTopic === t
                        ? "bg-primary text-white border-primary font-bold shadow-sm"
                        : "bg-slate-100 dark:bg-slate-900/60 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-800 hover:border-primary/40"
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>

            <form className="space-y-lg" onSubmit={handleSubmit}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-lg">
                <div className="space-y-xs">
                  <label className="block font-label-md text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                    Your Name
                  </label>
                  <input
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl px-md py-2.5 font-body-md text-slate-900 dark:text-white placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-primary/30 transition-all"
                    placeholder="Jane Doe"
                    type="text"
                  />
                </div>
                <div className="space-y-xs">
                  <label className="block font-label-md text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                    Work Email
                  </label>
                  <input
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl px-md py-2.5 font-body-md text-slate-900 dark:text-white placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-primary/30 transition-all"
                    placeholder="jane@enterprise.com"
                    type="email"
                  />
                </div>
              </div>

              <div className="space-y-xs">
                <div className="flex justify-between items-center">
                  <label className="block font-label-md text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                    Message
                  </label>
                  <span className="text-[11px] text-slate-400 dark:text-slate-500">
                    {message.length} / 1000 chars
                  </span>
                </div>
                <textarea
                  required
                  maxLength={1000}
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  className="w-full bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl px-md py-2.5 font-body-md text-slate-900 dark:text-white placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-primary/30 transition-all resize-none"
                  placeholder="Tell us about your document pipeline or deployment needs..."
                  rows={5}
                />
              </div>

              <button
                type="submit"
                disabled={formStatus !== "idle" || !name || !email || !message}
                className={`w-full md:w-auto font-label-md text-xs font-bold px-xl py-3 rounded-xl transition-all shadow-md active:scale-95 disabled:opacity-40 ${
                  formStatus === "sent"
                    ? "bg-emerald-600 text-white"
                    : "bg-primary hover:bg-primary-container text-white"
                }`}
              >
                {formStatus === "idle" && "Send Inquiry"}
                {formStatus === "sending" && "Processing..."}
                {formStatus === "sent" && "Inquiry Received ✓"}
              </button>
            </form>
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
