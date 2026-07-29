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
            className="w-8 h-8 rounded-lg object-contain"
            src="https://lh3.googleusercontent.com/aida-public/AB6AXuD49ygGQWTc4p3jjppKa6FymieNk8qc1Z1BhonLP0twZKlqnB9odZuE5OvQBvsgsPuvvRJsbwOfehs8mvK_KXR83KkG7CFefcNehUt0mSG_oJB5gvIq788HxvrCYRna3t2Hs9iq1P6oDSSilIaBGFt-MxVvmjkOq8vWp3xpFAavdHUU_dWPNE7AczUsoJTVjv_UG-CUsadzX1BHQAkmj_bNCFwot1FNgALljFtvGNs4LdtR_3NwcTPBkVdZvUchkcXrhDiD_Y1C9Mll"
            width={32}
            height={32}
            unoptimized
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
                  ? "text-on-background dark:text-white border-b-2 border-primary pb-1"
                  : "text-on-background/70 dark:text-white/70 hover:text-primary dark:hover:text-white"
              }`}
            >
              {link.label}
            </Link>
          ))}
        </nav>
      </div>
      <div className="flex items-center gap-md">
        <button
          onClick={toggle}
          className="w-10 h-10 rounded-full hover:bg-black/5 dark:hover:bg-white/10 flex items-center justify-center transition-all"
          title="Toggle theme"
        >
          <span className="material-symbols-outlined text-[20px]">
            {theme === "light" ? "dark_mode" : "light_mode"}
          </span>
        </button>
        <button className="font-label-md text-label-md text-on-background/70 dark:text-white/70 hover:text-primary dark:hover:text-white transition-colors">
          Sign In
        </button>
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
