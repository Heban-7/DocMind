"use client";

import { useState, useEffect } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import Navbar from "@/components/layout/Navbar";
import Footer from "@/components/layout/Footer";
import WebGLBackground from "@/components/landing/WebGLBackground";
import { useAuth } from "@/context/AuthContext";

const capabilities = [
  {
    title: "Page-by-Page Reading & Cost-Aware Routing",
    desc: "Each page is read the cheapest way that works: its text layer, a layout model for tables, OCR for scans, and a vision model only for pages the others fail on. Every page is logged with its engine, confidence, time and cost.",
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
    desc: "Chunks follow the document's own sections and keep their headings as context, and search combines meaning with exact words.",
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
    desc: "Table figures are stored as typed facts with sign, scale and period, so totals and changes are computed by the database instead of guessed by a model.",
    img: "/Structured_FactTableAndSQLQueryExecution.png",
    alt: "FactTable",
  },
  {
    title: "Audit Mode and a Number Checker",
    desc: "Every number in an answer is matched against the evidence it cites; a sentence whose figure the evidence does not hold is removed. In Audit Mode, any sentence without a citation is removed too.",
    img: "/Zero-TrustAuditMode(Anti-HallucinationGuardrail).png",
    alt: "Zero-Trust Audit",
  },
  {
    title: "Spatial Provenance & Bounding Box Citations",
    desc: "Open a citation and the page opens with a box on the table cell or paragraph that prints the figure, not just a page number.",
    img: "/SpatialProvenanceAndBoundingBoxCitations.png",
    alt: "Spatial Provenance",
  },
  {
    title: "Multi-Document Federated Search & Context",
    desc: "Search across your entire library simultaneously while maintaining a persistent conversational context for deep, multi-source analysis.",
    img: "/Multi-DocumentFederatedSearchAndConversationalMemory.png",
    alt: "Federated Search",
  },
];

const advantages = [
  { icon: "account_tree", title: "Page-Level Routing", desc: "Text layer, layout model, OCR or vision, chosen per page and logged with its cost." },
  { icon: "segment", title: "Context-Aware Chunking", desc: "Preserves financial tables and complex multi-column reading orders intact." },
  { icon: "verified", title: "Checked Citations", desc: "Every figure is matched to its evidence and boxed on the page that prints it." },
];

const heroImages = [
  {
    src: "https://lh3.googleusercontent.com/aida-public/AB6AXuCK3ChtdvMBnB-2jTMAALqplO__6ZA21fe2od35atzWrIg23Zp2KOjPY_hHmNePGqMcdCLxHlSIqPsZdK6rFcYrwMinK62WeEN0NTHUvRF4iDSZxM41Yslm2e5l6rTFU1U5k-KnEMkaE6w5Bs9aNvTlJBXIZY-I7blLErZLSDWvxMe3D7jDeRlXmYCnDgIAc1RqNagRs2PB596VPxxp1_YzbQQOQV124yh7Q-5eiRUTvnrmrY5K6ZGZC9CXlbQ3xO66J77WSnHs4WOZ",
    alt: "DocMind Intelligence Workspace",
  },
  {
    src: "/DocMind Homepage.png",
    alt: "DocMind Enterprise Document Refinery",
  },
];

export default function LandingPage() {
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const [currentHeroIndex, setCurrentHeroIndex] = useState(0);

  // Auto-play horizontal image slide every 5 seconds
  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentHeroIndex((prev) => (prev + 1) % heroImages.length);
    }, 5000);
    return () => clearInterval(timer);
  }, []);

  const handleTryRefinery = () => {
    if (isAuthenticated) {
      router.push("/dashboard");
    } else {
      router.push("/login?redirect=/dashboard");
    }
  };

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
              <button
                onClick={handleTryRefinery}
                className="bg-primary text-white h-14 px-xl rounded-lg font-label-md text-label-md font-bold flex items-center gap-sm hover:opacity-90 transition-opacity shadow-md cursor-pointer"
              >
                Try the Refinery
                <span className="material-symbols-outlined">arrow_forward</span>
              </button>
              <button
                onClick={() => {
                  const el = document.getElementById("hero-section");
                  el?.scrollIntoView({ behavior: "smooth" });
                }}
                className="border border-slate-300 dark:border-white/20 text-slate-900 dark:text-white h-14 px-xl rounded-lg font-label-md text-label-md font-medium hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer"
              >
                View Architecture
              </button>
            </div>

            {/* Horizontal Interchangeable Hero Carousel */}
            <div className="mt-xl max-w-5xl mx-auto relative group hero-float">
              <div className="rounded-2xl overflow-hidden shadow-2xl border border-black/10 dark:border-white/10 glass-card">
                <div
                  className="flex transition-transform duration-700 ease-in-out w-full"
                  style={{ transform: `translateX(-${currentHeroIndex * 100}%)` }}
                >
                  {heroImages.map((img, idx) => (
                    <div key={idx} className="w-full flex-shrink-0 relative aspect-[16/9]">
                      <Image
                        alt={img.alt}
                        className="w-full h-full object-cover"
                        src={img.src}
                        width={1280}
                        height={720}
                        unoptimized
                        priority={idx === 0}
                      />
                    </div>
                  ))}
                </div>
              </div>

              {/* Slide Indicator Dots */}
              <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-2 bg-black/60 backdrop-blur-md px-3 py-1.5 rounded-full z-20 border border-white/20 shadow-md">
                {heroImages.map((_, idx) => (
                  <button
                    key={idx}
                    onClick={() => setCurrentHeroIndex(idx)}
                    className={`h-2 rounded-full transition-all cursor-pointer ${
                      idx === currentHeroIndex ? "bg-white w-6" : "bg-white/40 hover:bg-white/70 w-2"
                    }`}
                    aria-label={`Slide ${idx + 1}`}
                  />
                ))}
              </div>

              {/* Prev / Next Slide Controls */}
              <button
                onClick={() => setCurrentHeroIndex((prev) => (prev === 0 ? heroImages.length - 1 : prev - 1))}
                className="absolute left-3 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-black/40 hover:bg-black/75 text-white backdrop-blur-md flex items-center justify-center transition-all opacity-0 group-hover:opacity-100 z-20 cursor-pointer border border-white/10 shadow-lg"
                aria-label="Previous Slide"
              >
                <span className="material-symbols-outlined text-xl">chevron_left</span>
              </button>
              <button
                onClick={() => setCurrentHeroIndex((prev) => (prev + 1) % heroImages.length)}
                className="absolute right-3 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-black/40 hover:bg-black/75 text-white backdrop-blur-md flex items-center justify-center transition-all opacity-0 group-hover:opacity-100 z-20 cursor-pointer border border-white/10 shadow-lg"
                aria-label="Next Slide"
              >
                <span className="material-symbols-outlined text-xl">chevron_right</span>
              </button>
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
              className={`flex flex-col ${
                i % 2 === 0 ? "md:flex-row" : "md:flex-row-reverse"
              } items-center gap-xl feature-interactive group`}
            >
              {/* Full Size Image Container */}
              <div className="w-full md:w-[48%] rounded-2xl overflow-hidden border border-black/10 dark:border-white/15 glass-card shadow-xl p-2 bg-slate-950/40 transition-transform duration-300 group-hover:scale-[1.01]">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  alt={cap.alt}
                  className="w-full h-auto object-contain rounded-xl block max-h-[420px] mx-auto"
                  src={cap.img}
                />
              </div>

              {/* Capability Description & Title (Note made smaller and cleaner) */}
              <div className={`w-full md:w-[52%] ${i % 2 === 0 ? "md:pl-xl" : "md:pr-xl"}`}>
                <h3 className="font-headline-lg text-2xl md:text-3xl text-slate-900 dark:text-white mb-md font-bold tracking-tight">
                  {cap.title}
                </h3>
                <p className="text-slate-700 dark:text-slate-300 text-lg md:text-xl leading-relaxed font-normal">
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
