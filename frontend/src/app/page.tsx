"use client";

import Image from "next/image";
import Link from "next/link";
import { ThemeProvider } from "@/components/ThemeProvider";
import Navbar from "@/components/layout/Navbar";
import Footer from "@/components/layout/Footer";
import WebGLBackground from "@/components/landing/WebGLBackground";

const capabilities = [
  {
    title: "Automated Document Triage & Cost-Optimized Routing",
    desc: "Intelligently categorize incoming documents and route them through optimized processing pipelines to balance precision and operational costs at scale.",
    img: "https://lh3.googleusercontent.com/aida/AP1WRLsgm6enLiSMuKDDs1xM7HqFgYuiJeW8o0QKw-MCdxchiV9CerPgFoCg6YgNVXj4-I5RxuBUMITE6GUuNIqCcXV9JFtrJm1IMxJSTcXXmBZlsYD7vtkX1m250fCAksEhvUSkdwFp0T7oy5ck4rK-XyeUs-iE6mcSikCnu4yKLD03x1Exd-N8OuxSwp8gtIdLrwWaghamfq0Ivs7JHowB38gZkiEwAIvWXcRtFqA6wf-Wao3cOk5Byli7L58",
    alt: "Automated Document Triage",
  },
  {
    title: "Layout-Aware Table & Multi-Column Extraction",
    desc: "Precision extraction of complex tabular data and multi-column layouts, preserving structural integrity and cell-level relationships.",
    img: "https://lh3.googleusercontent.com/aida/AP1WRLt5TelhKWVo_T3yPW3nnGi_ILICx7lcXSV-LPmgpmtm5lDdw_9Xfa74TzWOnxWNyMe120mz7nRhn4MPB9jvEbh_vjgyTv1cETNaLQGdwUuABTj9Oxjv-M4pJtxhkFhVrt4CBwx0Y_ORCqPvtDUIe7_k0yp9Fs7IRNZXs7zX6Sv13QWXcJKv4uVF-ABnORmBhvSh5Rptkmj5FGpj0F1Z3Tap4Qj_t4si-TborWePtJI24PlZ7nwyQPY_C5iL",
    alt: "Table Extraction",
  },
  {
    title: "Context-Aware Semantic Chunking (Logical Units)",
    desc: "Moving beyond simple character counts. We fragment documents into semantically coherent units to ensure RAG pipelines maintain perfect context.",
    img: "https://lh3.googleusercontent.com/aida/AP1WRLsVIp4iRpsu0rtD3UfVac20cQ2VY9sPohJ9q5wgvpV1gxkch-gQViA21hhmHSvH8I7y5LGz1T0O5VzrKzHYuyKlttV4n4DezVrsaGgdKkz6Rs8FJfB58N7zcOHK2FJNNnul43xqnWHQISdA5PProIMmDGRqENucGg5W-XkUR_tg-kwIpqOrGJJlVxmEcSPlAIwKOs9Kk6ymv3gROiJZbFI8gy1XspqEoESa_pysDp7nluQovXWqsG9JLQA9",
    alt: "Semantic Chunking",
  },
  {
    title: "Hierarchical PageIndex Tree Traversal",
    desc: "Navigate massive documents via a structured index tree, enabling rapid discovery of nested sections and cross-referenced appendices.",
    img: "https://lh3.googleusercontent.com/aida/AP1WRLvtb-0qCrzQBzRkDsyC0_3oofSkd9FvL2bLapk-g_qZrZI7-K2h6EiL7K3eK4LvHJ0QL3lmgNWOUeL2AlWa_XHVMjvdPmzpRulAbYBAubxeDd-234zHPGRL-dNa2lOTO0Wmbi4d1Ptc7Kc3HrDg4JJCDrLjYmtyGYlQnuAAkcIg_OFT1E95zJWzgUmm1Xdn0Zn72AIyrt0ZD8zhhcqdL1xWfAlMjUfrvD0r1O_gCF1IC8T8qHCAJ2xhOag",
    alt: "PageIndex Tree",
  },
  {
    title: "Structured FactTable & SQL Query Execution",
    desc: "Convert unstructured paragraphs into rigid FactTables, allowing you to run complex SQL queries directly against your document set.",
    img: "https://lh3.googleusercontent.com/aida/AP1WRLvC4Hh1ATxZnVpeeDHAqR0JcI0PECDFYnxaCAId6EjK0GZeP5DuUT7AUJmvaPgfVNO1RcZ8Glqkw_r2QICHFQS4zGyPz1lvdkXnmVAm4KArl1bIWMnSwPhMXM3nJHMGNf9zQSCRx6_x-Q0Y8R984xXzYXKTh0PN243kFvdtLFxa4-fJZBNxQH_8jdd-J9bT6gXmJu_qmd4gkunyKwg98JGRfcVzoKcXSvtr4NSuz_dzR9G9RGP_2VmFKvjj",
    alt: "FactTable",
  },
  {
    title: "Zero-Trust Audit Mode (Hallucination Guardrail)",
    desc: "Enterprise-grade verification layers that cross-reference every AI claim with source evidence, effectively eliminating hallucinations.",
    img: "https://lh3.googleusercontent.com/aida/AP1WRLsP46HV228_qmTyeOYARpj71D3tKeYn-bg6XexRxlK6OR2FSbeaCol3k6te9Aqj_tS3tkUsiW59k5IWfzWwd7-DjrmUFxoq6XZQQqW0BI_tmAOW_APWrHGLpA74u1fi7M9V8YVPJdNKbDdNoH_IhByMoCmrntwIcW6EGlaCkc3YZPDbmBiqaIWoTaSfSqk2xCm7qqKoeylH0iFAADxGOI8ohCrA2xzdZE0JMBpMx9OZKWcMpznwypIuLuic",
    alt: "Zero-Trust Audit",
  },
  {
    title: "Spatial Provenance & Bounding Box Citations",
    desc: "Don't just trust the answer—see exactly where it came from with pixel-perfect bounding box citations on the original page.",
    img: "https://lh3.googleusercontent.com/aida/AP1WRLsbhLPU3EUnXlByvRtHoEcRXGz6E9fIZX89vxKN1gPsSqMZVApftDxaYx_pbZBAu-kIQYsBRJwcYaJK-H2YUOHS3i56hZAZFb7AdGPBj_DdYDnHt21wYCd-3M5e66en0_HGT9M8wo_3_oL8zWKErkdKA9Y4QPQObW7R_T6gTIsrPYuClHjc3xwhUDp6xzvc9U_MEKSiNdk0RlkQRt7IIDuXqFvr9XNbJK8EsnxhdK-6FbRcZpIddUdVTg4j",
    alt: "Spatial Provenance",
  },
  {
    title: "Multi-Document Federated Search & Context",
    desc: "Search across your entire library simultaneously while maintaining a persistent conversational context for deep, multi-source analysis.",
    img: "https://lh3.googleusercontent.com/aida/AP1WRLswLHRPKcY2SdXWHyqDSjY2PpX7p_28t7WBPYV3N_Nw4iCx3-UG5_qVmcZ8MM2FF6qdm6JujKOPqtiRiFb3FJPgt4tSr9Hisz5Hda6VFXs55pKPOYXISSJgWgdSNU62k1GV1aNfGUzpuaDSPfeVivzpeiKYOzFszTt6SRy95EwaClUw-tNLQY5JzOd0tuIo5-qhmASK6Jabm6bjVdG1oI8-oEOhQM11lW_eeTsvYEYAzgn7ihpb3Frvtezp",
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
    <ThemeProvider>
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
            <h1 className="font-display text-display text-on-background dark:text-white max-w-4xl mx-auto mb-lg tracking-tight">
              Transform Unstructured Document Chaos into Auditable Intelligence.
            </h1>
            <p className="font-body-lg text-body-lg text-on-background/70 dark:text-white/70 max-w-2xl mx-auto mb-xl leading-relaxed">
              An agentic AI pipeline that ingests complex PDFs, financial reports, and scanned files with spatial provenance and zero-trust verification.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-md">
              <Link
                href="/dashboard"
                className="bg-primary text-white h-14 px-xl rounded-lg font-label-md text-label-md font-bold flex items-center gap-sm hover:opacity-90 transition-opacity"
              >
                Try the Refinery
                <span className="material-symbols-outlined">arrow_forward</span>
              </Link>
              <button className="border border-black/20 dark:border-white/20 text-on-background dark:text-white h-14 px-xl rounded-lg font-label-md text-label-md font-medium hover:bg-black/5 dark:hover:bg-white/5 transition-colors">
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
            <h2 className="font-display text-4xl text-on-background dark:text-white mb-md">
              Key Advantages
            </h2>
            <div className="h-1 w-20 bg-primary mx-auto rounded-full" />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-lg">
            {advantages.map((a) => (
              <div
                key={a.title}
                className="bg-white dark:bg-white/5 p-lg rounded-2xl border border-black/5 dark:border-white/10 shadow-sm hover:shadow-md transition-shadow group"
              >
                <div className="w-12 h-12 bg-primary/10 rounded-xl flex items-center justify-center mb-md group-hover:scale-110 transition-transform">
                  <span className="material-symbols-outlined text-primary">{a.icon}</span>
                </div>
                <h3 className="font-headline-md text-xl mb-sm">{a.title}</h3>
                <p className="text-on-background/70 dark:text-white/70">{a.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ── Core Engine Capabilities ── */}
        <section className="max-w-[1280px] mx-auto px-lg py-xl space-y-24">
          <div className="text-center mb-xl">
            <h2 className="font-display text-5xl text-on-background dark:text-white mb-md">
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
              <div className="w-full md:w-2/5 rounded-2xl overflow-hidden border border-black/5 dark:border-white/10 glass-card shadow-lg">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  alt={cap.alt}
                  className="w-full aspect-video object-cover"
                  src={cap.img}
                />
              </div>
              <div className={`w-full md:w-3/5 ${i % 2 === 0 ? "md:pl-lg" : "md:pr-lg"}`}>
                <h3 className="font-headline-lg text-4xl text-on-background dark:text-white mb-lg font-bold">
                  {cap.title}
                </h3>
                <p className="text-on-background/80 dark:text-white/80 text-xl md:text-2xl leading-relaxed">
                  {cap.desc}
                </p>
              </div>
            </div>
          ))}
        </section>
      </main>

      <Footer />
    </ThemeProvider>
  );
}
