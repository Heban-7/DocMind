"use client";

import { useState } from "react";
import Navbar from "@/components/layout/Navbar";
import Footer from "@/components/layout/Footer";

const techStack = [
  {
    name: "Python 3.13",
    icon: "code",
    category: "Backend Core",
    desc: "Type-safe asynchronous engine powering the Refinery pipeline.",
  },
  {
    name: "FastAPI Gateway",
    icon: "bolt",
    category: "API Layer",
    desc: "High-performance REST API supporting file streams & thread state.",
  },
  {
    name: "LangGraph Memory",
    icon: "account_tree",
    category: "Agent State",
    desc: "Cyclic multi-agent orchestrator backed by SQLite checkpointers.",
  },
  {
    name: "ChromaDB Store",
    icon: "database",
    category: "Vector Index",
    desc: "Dense semantic vector indexing for multi-document LDUs.",
  },
  {
    name: "Next.js 16",
    icon: "layers",
    category: "Frontend UI",
    desc: "Focus-first glassmorphic architecture built with React 19.",
  },
];

const archTabs = [
  {
    id: "triage",
    title: "1. Automated Triage",
    icon: "speed",
    detail:
      "Inspects PDF origin, vector density, and layout complexity to route documents into optimal cost & speed execution tiers (Fast, Standard, Premium).",
  },
  {
    id: "extract",
    title: "2. Layout-Aware Extraction",
    icon: "table_chart",
    detail:
      "Preserves multi-column reading order and cell-level table relationships without structure collapse.",
  },
  {
    id: "chunk",
    title: "3. Logical Unit Chunking",
    icon: "segment",
    detail:
      "Fragments text on logical document boundaries (~450 target words) to ensure RAG retrieval retains full context.",
  },
  {
    id: "audit",
    title: "4. Zero-Trust Audit",
    icon: "verified",
    detail:
      "Cross-references generated answers against spatial bounding box citations on original document pages.",
  },
];

export default function AboutPage() {
  const [activeTech, setActiveTech] = useState<string | null>(null);
  const [activeArch, setActiveArch] = useState<string>("triage");

  const currentArch = archTabs.find((a) => a.id === activeArch) || archTabs[0];

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-[#03050f] text-slate-900 dark:text-white transition-colors">
      <Navbar />

      <main className="pt-28 pb-xl px-margin-mobile md:px-lg max-w-[1200px] mx-auto min-h-screen">
        {/* Bento Layout Hero */}
        <div className="bento-grid gap-lg">
          {/* Profile Card */}
          <div className="col-span-1 md:col-span-4 h-full">
            <div className="bg-white dark:bg-[#0c1021] p-lg rounded-2xl border border-slate-200 dark:border-slate-800 flex flex-col items-center text-center h-full hover:border-primary/50 transition-all shadow-md">
              <div className="w-44 h-44 md:w-48 md:h-48 rounded-full overflow-hidden mb-lg border-4 border-primary/30 p-1.5 shadow-xl transition-transform duration-300 hover:scale-105">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  className="w-full h-full object-cover rounded-full"
                  alt="Liul Teshome — Systems Architect & Founder"
                  src="https://lh3.googleusercontent.com/aida-public/AB6AXuCXXaYuH-XGg29hnT8g_s3v6H_PUCEgF7l1JjdryX4gRFtFRJk_au1de6Caq4Wgxmy1bzRDvQLsObtN6R_j6hmKT8yHf4p4WL0q69BqlWELpaY0ztshFOtLmg62qEhWaiAZ1DpgbbcSutPzi7A_FZDPwm7F19rby9tFEHNIXcBBZP6YM3ucWeZeUM7mFschQx3lapTnYRe006frxXv5QRvLryqQ2To9_npaS3Z24v2VzZ6Pdu6en6wGvl_o8inZP7NRJStMnqudQN5t"
                />
              </div>
              <h1 className="font-headline-lg text-2xl font-bold text-slate-900 dark:text-white mb-xs">
                Liul Teshome
              </h1>
              <p className="font-label-md text-sm font-bold text-primary mb-md">
                Systems Architect &amp; Founder
              </p>
              <div className="flex gap-md justify-center mb-lg">
                <a
                  className="w-9 h-9 rounded-full bg-slate-100 dark:bg-white/10 flex items-center justify-center text-slate-700 dark:text-slate-200 hover:text-primary hover:bg-primary/10 transition-all"
                  href="mailto:liuljima1896@gmail.com"
                  title="Email"
                >
                  <span className="material-symbols-outlined text-[18px]">mail</span>
                </a>
                <a
                  className="w-9 h-9 rounded-full bg-slate-100 dark:bg-white/10 flex items-center justify-center text-slate-700 dark:text-slate-200 hover:text-primary hover:bg-primary/10 transition-all"
                  href="https://www.linkedin.com/in/liul-j-teshome"
                  target="_blank"
                  rel="noreferrer"
                  title="LinkedIn"
                >
                  <span className="material-symbols-outlined text-[18px]">link</span>
                </a>
                <a
                  className="w-9 h-9 rounded-full bg-slate-100 dark:bg-white/10 flex items-center justify-center text-slate-700 dark:text-slate-200 hover:text-primary hover:bg-primary/10 transition-all"
                  href="https://github.com/Heban-7"
                  target="_blank"
                  rel="noreferrer"
                  title="GitHub"
                >
                  <span className="material-symbols-outlined text-[18px]">terminal</span>
                </a>
              </div>
              <p className="font-body-sm text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
                Dedicated to bridging the gap between unstructured document chaos and enterprise-grade intelligence. Building the future of contextual reasoning.
              </p>
            </div>
          </div>

          {/* Mission Section */}
          <div className="col-span-1 md:col-span-8">
            <div className="bg-white dark:bg-[#0c1021] p-xl rounded-2xl border border-slate-200 dark:border-slate-800 h-full relative overflow-hidden flex flex-col justify-between shadow-md">
              <div className="absolute top-0 right-0 w-64 h-64 opacity-5 pointer-events-none text-slate-900 dark:text-white">
                <span className="material-symbols-outlined text-[140px]">architecture</span>
              </div>
              <div>
                <span className="font-label-md text-xs font-bold text-primary uppercase tracking-widest mb-xs block">
                  Architectural Pillars
                </span>
                <h2 className="font-display text-2xl md:text-3xl font-bold text-slate-900 dark:text-white leading-tight mb-lg max-w-2xl">
                  Solving Structure Collapse, Context Poverty, and Provenance Blindness.
                </h2>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-md">
                <div className="p-md rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 hover:border-primary/40 transition-all">
                  <div className="flex items-center gap-xs text-primary mb-xs font-bold text-xs">
                    <span className="material-symbols-outlined text-[18px]">grid_view</span>
                    <span>Structure Collapse</span>
                  </div>
                  <p className="font-body-sm text-[12px] text-slate-600 dark:text-slate-300 leading-relaxed">
                    Preventing table fragmentation and reading order destruction during PDF ingestion.
                  </p>
                </div>
                <div className="p-md rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 hover:border-primary/40 transition-all">
                  <div className="flex items-center gap-xs text-primary mb-xs font-bold text-xs">
                    <span className="material-symbols-outlined text-[18px]">history_edu</span>
                    <span>Context Poverty</span>
                  </div>
                  <p className="font-body-sm text-[12px] text-slate-600 dark:text-slate-300 leading-relaxed">
                    Ensuring every query maintains persistent conversation state via LangGraph.
                  </p>
                </div>
                <div className="p-md rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 hover:border-primary/40 transition-all">
                  <div className="flex items-center gap-xs text-primary mb-xs font-bold text-xs">
                    <span className="material-symbols-outlined text-[18px]">verified_user</span>
                    <span>Provenance Blindness</span>
                  </div>
                  <p className="font-body-sm text-[12px] text-slate-600 dark:text-slate-300 leading-relaxed">
                    Backing every AI answer with pixel-perfect bounding box source citations.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Interactive Technology Stack */}
          <div className="col-span-1 md:col-span-12 my-md">
            <div className="bg-white dark:bg-[#0c1021] p-xl rounded-2xl border border-slate-200 dark:border-slate-800 shadow-md">
              <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-md mb-lg">
                <div>
                  <h3 className="font-headline-md text-xl font-bold text-slate-900 dark:text-white">
                    The Intelligence Stack
                  </h3>
                  <p className="font-body-sm text-xs text-slate-600 dark:text-slate-400">
                    Click any technology module below to inspect its system role.
                  </p>
                </div>
                <a
                  href="https://github.com/Heban-7/DocMind"
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-xs text-primary font-label-md text-xs font-bold hover:underline"
                >
                  <span>Explore Source Code</span>
                  <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
                </a>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-md">
                {techStack.map((tech) => (
                  <button
                    key={tech.name}
                    onClick={() => setActiveTech(activeTech === tech.name ? null : tech.name)}
                    className={`p-md rounded-xl border transition-all text-left flex flex-col justify-between h-36 ${
                      activeTech === tech.name
                        ? "bg-primary text-white border-primary shadow-lg scale-105"
                        : "bg-slate-50 dark:bg-slate-900/60 border-slate-200 dark:border-slate-800 hover:border-primary/50 text-slate-900 dark:text-white"
                    }`}
                  >
                    <div className="flex items-center justify-between w-full">
                      <span className="material-symbols-outlined text-[24px]">
                        {tech.icon}
                      </span>
                      <span className="text-[10px] uppercase tracking-wider opacity-70">
                        {tech.category}
                      </span>
                    </div>
                    <div>
                      <h4 className="font-label-md font-bold text-sm mb-0.5">{tech.name}</h4>
                      <p className="text-[11px] opacity-80 line-clamp-2">{tech.desc}</p>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Interactive Pipeline Architecture Breakdown */}
          <div className="col-span-1 md:col-span-12">
            <div className="bg-white dark:bg-[#0c1021] p-xl rounded-2xl border border-slate-200 dark:border-slate-800 shadow-md">
              <div className="mb-lg">
                <span className="font-label-md text-xs font-bold text-primary uppercase tracking-widest block mb-xs">
                  Refinery Pipeline Interactive Tour
                </span>
                <h3 className="font-headline-md text-xl font-bold text-slate-900 dark:text-white">
                  How DocMind Processes Complex Documents
                </h3>
              </div>

              {/* Step Tabs */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-xs bg-slate-100 dark:bg-slate-900 p-1 rounded-xl mb-lg border border-slate-200 dark:border-slate-800">
                {archTabs.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveArch(tab.id)}
                    className={`flex items-center justify-center gap-xs py-2 px-md rounded-lg font-label-md text-xs transition-all ${
                      activeArch === tab.id
                        ? "bg-primary text-white font-bold shadow-md"
                        : "text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white"
                    }`}
                  >
                    <span className="material-symbols-outlined text-[16px]">{tab.icon}</span>
                    <span>{tab.title}</span>
                  </button>
                ))}
              </div>

              {/* Step Detail Card */}
              <div className="p-lg rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 flex items-start gap-md">
                <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center flex-shrink-0">
                  <span className="material-symbols-outlined text-[24px]">
                    {currentArch.icon}
                  </span>
                </div>
                <div>
                  <h4 className="font-headline-md text-base font-bold text-slate-900 dark:text-white mb-xs">
                    {currentArch.title}
                  </h4>
                  <p className="font-body-md text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
                    {currentArch.detail}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
