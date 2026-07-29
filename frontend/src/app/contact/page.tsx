"use client";

import Link from "next/link";
import { useState } from "react";
import Navbar from "@/components/layout/Navbar";
import Footer from "@/components/layout/Footer";

export default function ContactPage() {
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
      <Navbar />

      {/* Main Content Canvas */}
      <main className="pt-24 px-gutter pb-xl min-h-screen flex flex-col items-center">

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

      <Footer />
    </>
  );
}

