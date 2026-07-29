import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "DocMind | Founder & Systems Architect",
  description: "Meet the founder and learn about the architectural philosophy behind DocMind Enterprise Document Intelligence.",
};

const techStack = [
  { name: "Python", icon: "code" },
  { name: "FastAPI", icon: "bolt" },
  { name: "LangGraph", icon: "account_tree" },
  { name: "ChromaDB", icon: "database" },
  { name: "Next.js", icon: "layers" },
];

export default function AboutPage() {
  return (
    <>
      {/* TopNavBar */}
      <header className="fixed top-0 w-full z-50 flex justify-between items-center px-lg h-16 bg-surface/70 backdrop-blur-xl border-b border-outline-variant/30">
        <div className="flex items-center gap-md">
          <Link href="/" className="font-headline-lg text-headline-lg font-bold text-on-surface">
            DocMind
          </Link>
        </div>
        <nav className="hidden md:flex items-center gap-xl">
          <Link className="font-label-md text-label-md text-primary border-b-2 border-primary pb-1" href="/about">
            About
          </Link>
          <Link className="font-label-md text-label-md text-secondary hover:text-primary-container transition-colors" href="/contact">
            Contact
          </Link>
        </nav>
        <div className="flex items-center gap-md">
          <Link href="/dashboard" className="bg-on-surface text-surface px-lg py-sm rounded-lg font-label-md text-label-md hover:opacity-90 transition-all">
            Sign In
          </Link>
        </div>
      </header>

      <main className="pt-24 pb-xl px-margin-mobile md:px-lg max-w-[1200px] mx-auto min-h-screen">
        {/* View Switcher */}
        <div className="flex justify-center mb-xl">
          <div className="inline-flex p-1 bg-surface-container-low rounded-xl border border-outline-variant/20">
            <button className="px-6 py-2 rounded-lg font-label-md text-label-md bg-secondary-container text-on-secondary-container font-bold transition-all">
              Founder
            </button>
          </div>
        </div>

        {/* Bento Layout Hero */}
        <div className="bento-grid">
          {/* Profile Card */}
          <div className="col-span-1 md:col-span-4 h-full">
            <div className="glass-card p-lg rounded-xl border border-outline-variant/30 flex flex-col items-center text-center h-full">
              <div className="w-32 h-32 rounded-full overflow-hidden mb-lg border-2 border-primary/20 p-1">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  className="w-full h-full object-cover rounded-full"
                  alt="Liul Teshome — Systems Architect & Founder"
                  src="https://lh3.googleusercontent.com/aida-public/AB6AXuCXXaYuH-XGg29hnT8g_s3v6H_PUCEgF7l1JjdryX4gRFtFRJk_au1de6Caq4Wgxmy1bzRDvQLsObtN6R_j6hmKT8yHf4p4WL0q69BqlWELpaY0ztshFOtLmg62qEhWaiAZ1DpgbbcSutPzi7A_FZDPwm7F19rby9tFEHNIXcBBZP6YM3ucWeZeUM7mFschQx3lapTnYRe006frxXv5QRvLryqQ2To9_npaS3Z24v2VzZ6Pdu6en6wGvl_o8inZP7NRJStMnqudQN5t"
                />
              </div>
              <h1 className="font-headline-lg text-headline-lg text-on-surface mb-xs">Liul Teshome</h1>
              <p className="font-label-md text-label-md text-primary mb-lg">Systems Architect &amp; Founder</p>
              <div className="flex gap-md justify-center mb-lg">
                <a className="text-on-surface-variant hover:text-primary transition-colors" href="mailto:liuljima1896@gmail.com" title="Email">
                  <span className="material-symbols-outlined">mail</span>
                </a>
                <a className="text-on-surface-variant hover:text-primary transition-colors" href="https://www.linkedin.com/in/liul-j-teshome" target="_blank" title="LinkedIn">
                  <span className="material-symbols-outlined">link</span>
                </a>
                <a className="text-on-surface-variant hover:text-primary transition-colors" href="https://github.com/Heban-7" target="_blank" title="GitHub">
                  <span className="material-symbols-outlined">terminal</span>
                </a>
              </div>
              <p className="font-body-sm text-body-sm text-on-surface-variant leading-relaxed">
                Dedicated to bridging the gap between unstructured data and enterprise-grade intelligence. Building the future of contextual reasoning.
              </p>
            </div>
          </div>

          {/* Mission Section */}
          <div className="col-span-1 md:col-span-8">
            <div className="glass-card p-xl rounded-xl border border-outline-variant/30 h-full relative overflow-hidden">
              <div className="absolute top-0 right-0 w-64 h-64 opacity-5 pointer-events-none">
                <span className="material-symbols-outlined text-[120px]">architecture</span>
              </div>
              <span className="font-label-md text-label-md text-primary uppercase tracking-widest mb-md block">
                Our Mission
              </span>
              <h2 className="font-display text-[32px] md:text-display text-on-surface leading-tight mb-xl max-w-2xl">
                Solving Structure Collapse, Context Poverty, and Provenance Blindness.
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-lg">
                <div className="space-y-sm">
                  <div className="flex items-center gap-xs text-primary">
                    <span className="material-symbols-outlined">grid_view</span>
                    <span className="font-label-md text-label-md font-bold">Structure Collapse</span>
                  </div>
                  <p className="font-body-sm text-body-sm text-on-surface-variant">
                    Preventing the loss of data hierarchy during ingestion and processing.
                  </p>
                </div>
                <div className="space-y-sm">
                  <div className="flex items-center gap-xs text-primary">
                    <span className="material-symbols-outlined">history_edu</span>
                    <span className="font-label-md text-label-md font-bold">Context Poverty</span>
                  </div>
                  <p className="font-body-sm text-body-sm text-on-surface-variant">
                    Ensuring every insight is grounded in the full history of the document set.
                  </p>
                </div>
                <div className="space-y-sm">
                  <div className="flex items-center gap-xs text-primary">
                    <span className="material-symbols-outlined">verified_user</span>
                    <span className="font-label-md text-label-md font-bold">Provenance Blindness</span>
                  </div>
                  <p className="font-body-sm text-body-sm text-on-surface-variant">
                    Providing absolute clarity on the source and validity of every AI output.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Tech Stack Grid */}
          <div className="col-span-1 md:col-span-12">
            <div className="glass-card p-lg rounded-xl border border-outline-variant/30">
              <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-md mb-lg">
                <div>
                  <h3 className="font-headline-md text-headline-md text-on-surface">The Intelligence Stack</h3>
                  <p className="font-body-sm text-body-sm text-on-surface-variant">
                    Engineered for precision, speed, and deep traceability.
                  </p>
                </div>
                <button className="flex items-center gap-sm text-primary font-label-md text-label-md group">
                  Full Documentation
                  <span className="material-symbols-outlined group-hover:translate-x-1 transition-transform">arrow_forward</span>
                </button>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-md">
                {techStack.map((tech) => (
                  <div
                    key={tech.name}
                    className="p-md bg-surface-container rounded-lg border border-outline-variant/20 flex flex-col items-center text-center group hover:bg-primary transition-all duration-300"
                  >
                    <div className="w-10 h-10 mb-sm flex items-center justify-center bg-surface-container-lowest rounded-full group-hover:bg-primary-container">
                      <span className="material-symbols-outlined text-primary group-hover:text-on-primary-container">
                        {tech.icon}
                      </span>
                    </div>
                    <span className="font-label-md text-label-md text-on-surface group-hover:text-on-primary">
                      {tech.name}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Architectural Philosophy */}
          <div className="col-span-1 md:col-span-7 h-full">
            <div className="glass-card p-xl rounded-xl border border-outline-variant/30 h-full">
              <h3 className="font-headline-md text-headline-md text-on-surface mb-md">Architectural Philosophy</h3>
              <p className="font-body-md text-body-md text-on-surface-variant mb-lg leading-relaxed">
                At DocMind, we believe that AI should be invisible until it is indispensable. Our systems are built on the principle of{" "}
                <strong className="text-on-surface">Atomic Context Preservation</strong>. We don&apos;t just extract text; we map the spatial and semantic relationships that give that text meaning.
              </p>
              <div className="flex flex-col gap-sm">
                {[
                  "Rigorous validation layers for every LLM inference.",
                  "Deterministic outcomes in non-deterministic environments.",
                  "End-to-end encryption for the most sensitive enterprise assets.",
                ].map((point, i) => (
                  <div key={i} className="flex items-start gap-md">
                    <div className="mt-1 w-2 h-2 rounded-full bg-primary flex-shrink-0" />
                    <p className="font-body-sm text-body-sm text-on-surface-variant">{point}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Visualization Card */}
          <div className="col-span-1 md:col-span-5 h-full">
            <div className="glass-card rounded-xl border border-outline-variant/30 overflow-hidden relative h-[400px] md:h-full">
              <div
                className="w-full h-full bg-cover bg-center"
                style={{
                  backgroundImage: `url('https://lh3.googleusercontent.com/aida-public/AB6AXuBxqM_HgtYGDuwymgHHFioVKDo20Fn5LCP-AUmhep8dO7_VMXuy6gYu_EpB6PkTmvXCdLDYKdQphKmXLbsCvvLPiNju_jzoIyCO9EJa4NbVtf70SiTbY0eXCrTPl2DUZfK_3j_0zHwTq-y_egRi3d2DiGnf9kMN9aCJk1HJLLgnxkcNc2SQw6yH3-j8LqAFztuJ6dK77XLbyzyWf8umOvJPddoj1BqPIQs1Fwipp8veKH13CPnQVLh6BOBAdT-s-M1GXtRSUlLIn5b1')`,
                }}
              >
                <div className="absolute inset-0 bg-gradient-to-t from-surface to-transparent p-lg flex flex-col justify-end">
                  <span className="font-label-md text-label-md text-primary font-bold">Network Visualization</span>
                  <p className="font-body-sm text-body-sm text-on-surface-variant">
                    Visualizing context links across 50,000+ document fragments in real-time.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="w-full py-xl px-lg flex flex-col md:flex-row justify-between items-center gap-md bg-surface border-t border-outline-variant/20">
        <div className="flex flex-col items-center md:items-start">
          <span className="font-headline-md text-headline-md font-bold text-on-surface mb-xs">DocMind</span>
          <p className="font-body-sm text-body-sm text-on-surface-variant/70">© 2024 DocMind Enterprise. All rights reserved.</p>
        </div>
        <div className="flex gap-lg">
          <Link className="font-label-md text-label-md text-on-surface-variant/70 hover:text-primary transition-colors" href="#">Privacy Policy</Link>
          <Link className="font-label-md text-label-md text-on-surface-variant/70 hover:text-primary transition-colors" href="#">Terms of Service</Link>
          <Link className="font-label-md text-label-md text-on-surface-variant/70 hover:text-primary transition-colors" href="#">Security</Link>
        </div>
      </footer>
    </>
  );
}
