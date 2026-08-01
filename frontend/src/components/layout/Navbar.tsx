"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useTheme } from "@/components/ThemeProvider";

export default function Navbar() {
  const pathname = usePathname();
  const { theme, toggle } = useTheme();

  const navLinks = [
    { href: "/", label: "Home" },
    { href: "/dashboard", label: "Dashboard" },
    { href: "/about", label: "About" },
    { href: "/contact", label: "Contact" },
  ];

  return (
    <header className="fixed top-0 w-full z-50 flex justify-between items-center px-lg h-16 bg-white/80 dark:bg-[#03050f]/60 backdrop-blur-xl border-b border-black/5 dark:border-white/10 transition-colors">
      <div className="flex items-center gap-xl">
        <Link href="/" className="flex items-center gap-sm">
          <Image
            alt="DocMind Logo"
            className="w-8 h-8 rounded-lg object-cover"
            src="/logo.jpg"
            width={32}
            height={32}
          />
          <span className="font-headline-lg text-lg font-bold text-primary dark:text-white tracking-tight">
            DocMind
          </span>
        </Link>

        <nav className="hidden md:flex gap-lg">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={`font-label-md text-label-md transition-colors ${
                pathname === link.href
                  ? "text-slate-900 dark:text-white font-bold border-b-2 border-primary pb-1"
                  : "text-slate-700 dark:text-slate-300 hover:text-primary dark:hover:text-white font-medium"
              }`}
            >
              {link.label}
            </Link>
          ))}
        </nav>
      </div>
      <div className="flex items-center gap-md">
        {pathname !== "/about" && pathname !== "/contact" && (
          <button
            onClick={toggle}
            className="w-10 h-10 rounded-full hover:bg-black/5 dark:hover:bg-white/10 flex items-center justify-center transition-all text-slate-800 dark:text-white"
            title="Toggle theme"
          >
            <span className="material-symbols-outlined text-[20px] text-slate-800 dark:text-white">
              {theme === "light" ? "dark_mode" : "light_mode"}
            </span>
          </button>
        )}


        <Link
          href="/login"
          className="font-label-md text-label-md text-slate-700 dark:text-slate-300 hover:text-primary dark:hover:text-white font-medium transition-colors"
        >
          Sign In
        </Link>


        <Link
          href="/dashboard"
          className="bg-primary text-white px-lg py-sm rounded-lg font-label-md text-label-md hover:scale-95 transition-all duration-150 ease-in-out"
        >
          Launch Dashboard
        </Link>
      </div>
    </header>
  );
}
