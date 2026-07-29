"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

const sidebarNav = [
  { href: "/", label: "Home", icon: "home" },
  { href: "/dashboard", label: "Dashboard", icon: "dashboard" },
  { href: "/about", label: "About", icon: "info" },
  { href: "/contact", label: "Contact", icon: "mail" },
];

export default function ContactPage() {
  const pathname = usePathname();
  const [formStatus, setFormStatus] = useState<"idle" | "sending" | "sent">("idle");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormStatus("sending");
    setTimeout(() => {
      setFormStatus("sent");
      setTimeout(() => setFormStatus("idle"), 3000);
    }, 1500);
  };

  return (
    <>
      {/* TopNavBar */}
      <header className="fixed top-0 w-full z-50 flex justify-between items-center px-lg h-16 bg-surface/70 backdrop-blur-xl border-b border-outline-variant/30">
        <div className="flex items-center gap-md">
          <Link href="/" className="font-headline-lg text-headline-lg font-bold text-on-surface">
            DocMind
          </Link>
          <nav className="hidden md:flex items-center gap-lg ml-xl">
            <Link className="font-label-md text-label-md text-secondary transition-colors hover:text-primary-container" href="/about">
              About
            </Link>
            <Link className="font-label-md text-label-md text-primary border-b-2 border-primary pb-1" href="/contact">
              Contact
            </Link>
          </nav>
        </div>
        <div className="flex items-center gap-md">
          <button className="font-label-md text-label-md px-md py-sm rounded-lg text-on-surface-variant/70 hover:text-primary transition-colors">
            Sign In
          </button>
          <Link
            href="/dashboard"
            className="bg-primary text-on-primary font-label-md text-label-md px-lg py-sm rounded-lg transition-transform active:scale-95 duration-150"
          >
            Get Started
          </Link>
        </div>
      </header>

      {/* Sidebar */}
      <aside className="fixed left-0 top-0 h-screen hidden md:flex flex-col py-lg w-[280px] bg-surface-container-low border-r border-outline-variant/30 z-40 pt-20">
        <div className="px-lg mb-xl">
          <h2 className="font-headline-md text-headline-md font-bold text-on-surface">DocMind AI</h2>
          <p className="font-body-sm text-body-sm text-on-surface-variant">Enterprise Intelligence</p>
        </div>
        <nav className="flex-1 px-md space-y-base">
          {sidebarNav.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-md px-4 py-2 rounded-lg transition-all ${
                pathname === item.href
                  ? "bg-secondary-container text-on-secondary-container font-bold translate-x-1 duration-200"
                  : "text-on-surface-variant hover:bg-surface-container-high"
              }`}
            >
              <span className="material-symbols-outlined">{item.icon}</span>
              <span className="font-label-md text-label-md">{item.label}</span>
            </Link>
          ))}
        </nav>
        <div className="px-md mt-auto pt-lg space-y-base">
          <Link href="#" className="flex items-center gap-md text-on-surface-variant px-4 py-2 hover:bg-surface-container-high transition-all rounded-lg">
            <span className="material-symbols-outlined">settings</span>
            <span className="font-label-md text-label-md">Settings</span>
          </Link>
          <Link href="#" className="flex items-center gap-md text-on-surface-variant px-4 py-2 hover:bg-surface-container-high transition-all rounded-lg">
            <span className="material-symbols-outlined">help</span>
            <span className="font-label-md text-label-md">Support</span>
          </Link>
        </div>
      </aside>

      {/* Main Content Canvas */}
      <main className="md:ml-[280px] pt-24 px-gutter pb-xl min-h-screen flex flex-col items-center">
        {/* View Switcher Tab Bar */}
        <div className="w-full max-w-[800px] mb-xl">
          <div className="flex items-center gap-sm bg-surface-container-low p-1 rounded-xl w-fit">
            <button className="px-lg py-sm font-label-md text-label-md bg-surface-container-lowest text-primary shadow-sm rounded-lg">
              Inquiry
            </button>
            <button className="px-lg py-sm font-label-md text-label-md text-secondary hover:text-primary transition-colors">
              Support
            </button>
            <button className="px-lg py-sm font-label-md text-label-md text-secondary hover:text-primary transition-colors">
              Partnership
            </button>
          </div>
        </div>

        {/* Headline */}
        <div className="w-full max-w-[800px] mb-xl">
          <h1 className="font-display text-display text-on-surface mb-sm">Let&apos;s connect.</h1>
          <p className="font-body-lg text-body-lg text-on-surface-variant max-w-lg">
            Our team of intelligence specialists is ready to help you scale your enterprise document processing.
          </p>
        </div>

        {/* Contact Layout */}
        <div className="w-full max-w-[800px] grid grid-cols-1 lg:grid-cols-12 gap-xl items-start">
          {/* Form */}
          <div className="lg:col-span-8 bg-surface-container-lowest border border-outline-variant/30 rounded-xl p-lg shadow-sm">
            <form className="space-y-lg" onSubmit={handleSubmit}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-lg">
                <div className="space-y-xs">
                  <label className="font-label-md text-label-md text-outline">Name</label>
                  <input
                    className="w-full bg-transparent border border-outline-variant rounded-lg px-md py-sm font-body-md focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition-all"
                    placeholder="Jane Doe"
                    type="text"
                  />
                </div>
                <div className="space-y-xs">
                  <label className="font-label-md text-label-md text-outline">Email</label>
                  <input
                    className="w-full bg-transparent border border-outline-variant rounded-lg px-md py-sm font-body-md focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition-all"
                    placeholder="jane@enterprise.com"
                    type="email"
                  />
                </div>
              </div>
              <div className="space-y-xs">
                <label className="font-label-md text-label-md text-outline">Industry Sector</label>
                <select className="w-full bg-transparent border border-outline-variant rounded-lg px-md py-sm font-body-md focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition-all appearance-none cursor-pointer">
                  <option>Financial Services</option>
                  <option>Legal &amp; Compliance</option>
                  <option>Healthcare</option>
                  <option>Government</option>
                  <option>Other</option>
                </select>
              </div>
              <div className="space-y-xs">
                <label className="font-label-md text-label-md text-outline">Message</label>
                <textarea
                  className="w-full bg-transparent border border-outline-variant rounded-lg px-md py-sm font-body-md focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition-all resize-none"
                  placeholder="Tell us about your document intelligence needs..."
                  rows={5}
                />
              </div>
              <button
                type="submit"
                disabled={formStatus !== "idle"}
                className={`w-full md:w-auto font-label-md text-label-md px-xl py-lg rounded-lg hover:brightness-110 transition-all active:scale-[0.98] ${
                  formStatus === "sent"
                    ? "bg-green-600 text-white"
                    : "bg-primary text-on-primary"
                }`}
              >
                {formStatus === "idle" && "Send Message"}
                {formStatus === "sending" && "Sending..."}
                {formStatus === "sent" && "Message Sent ✓"}
              </button>
            </form>
          </div>

          {/* Side Info */}
          <div className="lg:col-span-4 space-y-xl">
            <div className="space-y-lg">
              <h3 className="font-label-md text-label-md text-outline uppercase tracking-widest">Connect</h3>
              <div className="flex flex-col gap-md">
                {[
                  { href: "mailto:liuljima1896@gmail.com", icon: "mail", label: "Email" },
                  { href: "https://github.com/Heban-7", icon: "terminal", label: "GitHub" },
                  { href: "https://www.linkedin.com/in/liul-j-teshome", icon: "share", label: "LinkedIn" },
                  { href: "https://x.com/linnet_ai", icon: "brand_awareness", label: "Twitter / X" },
                ].map((link) => (
                  <a key={link.label} className="flex items-center gap-md group" href={link.href} target="_blank">
                    <div className="w-10 h-10 rounded-full bg-surface-container-high flex items-center justify-center group-hover:bg-primary-container group-hover:text-on-primary-container transition-all">
                      <span className="material-symbols-outlined text-[20px]">{link.icon}</span>
                    </div>
                    <span className="font-body-md text-body-md text-on-surface-variant group-hover:text-primary transition-colors">
                      {link.label}
                    </span>
                  </a>
                ))}
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="md:ml-[280px] w-auto py-xl px-lg flex flex-col md:flex-row justify-between items-center gap-md border-t border-outline-variant/20 bg-surface">
        <div className="flex flex-col items-center md:items-start gap-xs">
          <span className="font-headline-md text-headline-md font-bold text-on-surface">DocMind</span>
          <p className="font-body-sm text-body-sm text-on-surface-variant/70">© 2024 DocMind Enterprise. All rights reserved.</p>
        </div>
        <div className="flex gap-lg">
          <Link className="font-label-md text-label-md text-on-surface-variant/70 hover:text-primary transition-colors opacity-80 hover:opacity-100" href="#">Privacy Policy</Link>
          <Link className="font-label-md text-label-md text-on-surface-variant/70 hover:text-primary transition-colors opacity-80 hover:opacity-100" href="#">Terms of Service</Link>
          <Link className="font-label-md text-label-md text-on-surface-variant/70 hover:text-primary transition-colors opacity-80 hover:opacity-100" href="#">Security</Link>
        </div>
      </footer>
    </>
  );
}
