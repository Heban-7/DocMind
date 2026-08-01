"use client";

import Image from "next/image";
import Link from "next/link";
import Navbar from "@/components/layout/Navbar";
import Footer from "@/components/layout/Footer";
import WebGLBackground from "@/components/landing/WebGLBackground";

const capabilities = [
  {
    title: "Automated Document Triage & Cost-Optimized Routing",
    desc: "Intelligently categorize incoming documents and route them through optimized processing pipelines to balance precision and operational costs at scale.",
    img: "/AutomatedDocumentTriageAndCost-Optimized Routing.png",
    alt: "Automated Document Triage",
  },
  {
    title: "Layout-Aware Table & Multi-Column Extraction",
    desc: "Precision extraction of complex tabular data and multi-column layouts, preserving structural integrity and cell-level relationships.",
    img: "/Layout-AwareTableAndMulti-ColumnExtraction.png",
    alt: "Table Extraction",
  },
  {
    title: "Context-Aware Semantic Chunking (Logical Units)",
    desc: "Moving beyond simple character counts. We fragment documents into semantically coherent units to ensure RAG pipelines maintain perfect context.",
    img: "/Context-AwareSemanticChunking(LogicalDocumentUnits).png",
    alt: "Semantic Chunking",
  },
  {
    title: "Hierarchical PageIndex Tree Traversal",
    desc: "Navigate massive documents via a structured index tree, enabling rapid discovery of nested sections and cross-referenced appendices.",
    img: "/HierarchicalPageIndexTreeTraversal.png",
    alt: "PageIndex Tree",
  },
  {
    title: "Structured FactTable & SQL Query Execution",
    desc: "Convert unstructured paragraphs into rigid FactTables, allowing you to run complex SQL queries directly against your document set.",
    img: "/Structured_FactTableAndSQLQueryExecution.png",
    alt: "FactTable",
  },
  {
    title: "Zero-Trust Audit Mode (Hallucination Guardrail)",
    desc: "Enterprise-grade verification layers that cross-reference every AI claim with source evidence, effectively eliminating hallucinations.",
    img: "/Zero-TrustAuditMode(Anti-HallucinationGuardrail).png",
    alt: "Zero-Trust Audit",
  },
  {
    title: "Spatial Provenance & Bounding Box Citations",
    desc: "Don't just trust the answer—see exactly where it came from with pixel-perfect bounding box citations on the original page.",
    img: "/Zero-TrustAuditMode(Anti-HallucinationGuardrail).png",
    alt: "Spatial Provenance",
  },
  {
    title: "Multi-Document Federated Search & Context",
    desc: "Search across your entire library simultaneously while maintaining a persistent conversational context for deep, multi-source analysis.",
    img: "/Zero-TrustAuditMode(Anti-HallucinationGuardrail).png",
    alt: "Federated Search",
  },
];


const advantages = [
  { icon: "account_tree", title: "Intelligent Triage", desc: "Automated document classification & cost-effective routing for enterprise scale." },
  { icon: "segment", title: "Context-Aware Chunking", desc: "Preserves financial tables and complex multi-column reading orders intact." },
  { icon: "verified", title: "Zero-Trust Provenance", desc: "Every answer backed by exact page numbers and spatial citations." },
];

export default function LandingPage() {
  return (
    <>
      <WebGLBackground />
      <Navbar />

      <main className="pt-32 relative z-10 w-full">
        {/* ── Hero Section ── */}
        <section className="max-w-[1280px] mx-auto px-lg text-center mb-xl" id="hero-section">
          <div className="hero-float inline-flex items-center gap-sm px-md py-xs rounded-full border border-black/10 dark:border-white/10 bg-black/5 dark:bg-white/5 mb-lg transition-transform duration-300">
            <span className="font-label-md text-label-md text-primary dark:text-primary-fixed-dim">
              DocMind: Talk to your Document.
            </span>
          </div>
          <div className="parallax-target">
            <h1 className="font-display text-display text-slate-900 dark:text-white max-w-4xl mx-auto mb-lg tracking-tight">
              Transform Unstructured Document Chaos into Auditable Intelligence.
            </h1>
            <p className="font-body-lg text-body-lg text-slate-700 dark:text-slate-300 max-w-2xl mx-auto mb-xl leading-relaxed">
              An agentic AI pipeline that ingests complex PDFs, financial reports, and scanned files with spatial provenance and zero-trust verification.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-md">
              <Link
                href="/dashboard"
                className="bg-primary text-white h-14 px-xl rounded-lg font-label-md text-label-md font-bold flex items-center gap-sm hover:opacity-90 transition-opacity shadow-md"
              >
                Try the Refinery
                <span className="material-symbols-outlined">arrow_forward</span>
              </Link>
              <button className="border border-slate-300 dark:border-white/20 text-slate-900 dark:text-white h-14 px-xl rounded-lg font-label-md text-label-md font-medium hover:bg-black/5 dark:hover:bg-white/5 transition-colors">
                View Architecture
              </button>
            </div>
            <div className="mt-xl max-w-5xl mx-auto rounded-2xl overflow-hidden shadow-lg border border-black/5 dark:border-white/10 glass-card hero-float">
              <Image
                alt="DocMind Dashboard Visualization"
                className="w-full h-auto object-cover"
                src="https://lh3.googleusercontent.com/aida-public/AB6AXuCK3ChtdvMBnB-2jTMAALqplO__6ZA21fe2od35atzWrIg23Zp2KOjPY_hHmNePGqMcdCLxHlSIqPsZdK6rFcYrwMinK62WeEN0NTHUvRF4iDSZxM41Yslm2e5l6rTFU1U5k-KnEMkaE6w5Bs9aNvTlJBXIZY-I7blLErZLSDWvxMe3D7jDeRlXmYCnDgIAc1RqNagRs2PB596VPxxp1_YzbQQOQV124yh7Q-5eiRUTvnrmrY5K6ZGZC9CXlbQ3xO66J77WSnHs4WOZ"
                width={1280}
                height={720}
                unoptimized
                priority
              />
            </div>
          </div>
        </section>

        {/* ── GitHub Banner ── */}
        <section className="w-full mb-xl">
          <a
            className="block w-full bg-[#24292f]/95 hover:bg-[#1b1f23] backdrop-blur-md py-6 transition-all duration-300 border-y border-white/5 group"
            href="https://github.com/Heban-7/DocMind"
            target="_blank"
            rel="noreferrer"
          >
            <div className="max-w-[1280px] mx-auto px-lg flex items-center justify-center gap-md">
              <svg className="w-8 h-8 fill-white group-hover:scale-110 transition-transform" viewBox="0 0 24 24">
                <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
              </svg>
              <span className="font-headline-md text-white text-xl md:text-2xl tracking-tight">
                100% Open Source: Fork &amp; Contribute on GitHub
              </span>
              <span className="material-symbols-outlined text-white/50 group-hover:translate-x-2 transition-transform">
                arrow_forward
              </span>
            </div>
          </a>
        </section>

        {/* ── Key Advantages ── */}
        <section className="max-w-[1280px] mx-auto px-lg py-xl mb-xl">
          <div className="text-center mb-xl">
            <h2 className="font-display text-4xl text-slate-900 dark:text-white mb-md">
              Key Advantages
            </h2>
            <div className="h-1 w-20 bg-primary mx-auto rounded-full" />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-lg">
            {advantages.map((a) => (
              <div
                key={a.title}
                className="bg-white dark:bg-white/5 p-lg rounded-2xl border border-slate-200 dark:border-white/10 shadow-sm hover:shadow-md transition-shadow group"
              >
                <div className="w-12 h-12 bg-primary/10 rounded-xl flex items-center justify-center mb-md group-hover:scale-110 transition-transform">
                  <span className="material-symbols-outlined text-primary">{a.icon}</span>
                </div>
                <h3 className="font-headline-md text-xl font-bold text-slate-900 dark:text-white mb-sm">
                  {a.title}
                </h3>
                <p className="text-slate-700 dark:text-slate-300">{a.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ── Core Engine Capabilities ── */}
        <section className="max-w-[1280px] mx-auto px-lg py-xl space-y-24">
          <div className="text-center mb-xl">
            <h2 className="font-display text-5xl text-slate-900 dark:text-white mb-md">
              Core Engine Capabilities
            </h2>
            <div className="h-1 w-32 bg-primary mx-auto rounded-full" />
          </div>
          {capabilities.map((cap, i) => (
            <div
              key={cap.title}
              className={`flex flex-col ${i % 2 === 0 ? "md:flex-row" : "md:flex-row-reverse"
                } items-center gap-xl feature-interactive group`}
            >
              <div className="w-full md:w-2/5 rounded-2xl overflow-hidden border border-black/5 dark:border-white/10 glass-card shadow-lg">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  alt={cap.alt}
                  className="w-full aspect-video object-cover"
                  src={cap.img}
                />
              </div>
              <div className={`w-full md:w-3/5 ${i % 2 === 0 ? "md:pl-lg" : "md:pr-lg"}`}>
                <h3 className="font-headline-lg text-4xl text-slate-900 dark:text-white mb-lg font-bold">
                  {cap.title}
                </h3>
                <p className="text-slate-700 dark:text-slate-300 text-xl md:text-2xl leading-relaxed">
                  {cap.desc}
                </p>
              </div>
            </div>
          ))}
        </section>
      </main>

      <Footer />
    </>
  );
}
