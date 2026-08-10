"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "@/components/ThemeProvider";
import { useAuth } from "@/context/AuthContext";

export default function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { theme, toggle } = useTheme();
  const { user, isAuthenticated, logout } = useAuth();

  const handleDashboardClick = (e: React.MouseEvent) => {
    e.preventDefault();
    if (isAuthenticated) {
      router.push("/dashboard");
    } else {
      router.push("/login?redirect=/dashboard");
    }
  };

  const navLinks = [
    { href: "/", label: "Home" },
    { href: "/dashboard", label: "Dashboard", onClick: handleDashboardClick },
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
            <a
              key={link.href}
              href={link.href}
              onClick={link.onClick || undefined}
              className={`font-label-md text-label-md cursor-pointer transition-colors ${
                pathname === link.href
                  ? "text-slate-900 dark:text-white font-bold border-b-2 border-primary pb-1"
                  : "text-slate-700 dark:text-slate-300 hover:text-primary dark:hover:text-white font-medium"
              }`}
            >
              {link.label}
            </a>
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

        {isAuthenticated && user ? (
          /* User Profile Avatar Badge on Top Right */
          <div className="relative group flex items-center">
            <div
              className="w-9 h-9 rounded-full bg-gradient-to-tr from-primary to-blue-500 text-white font-bold text-sm flex items-center justify-center shadow-md cursor-pointer border-2 border-white dark:border-slate-800 transition-transform group-hover:scale-105"
              title={user.email}
            >
              {user.email.charAt(0).toUpperCase()}
            </div>

            {/* Hover Tooltip displaying email & Sign Out */}
            <div className="absolute right-0 top-11 hidden group-hover:flex flex-col items-end min-w-[200px] bg-white dark:bg-[#0c1021] border border-slate-200 dark:border-slate-800 rounded-xl p-3 shadow-xl z-50 fade-in">
              <span className="text-xs font-semibold text-slate-900 dark:text-white truncate max-w-[180px]">
                {user.email}
              </span>
              <span className="text-[10px] text-slate-400 dark:text-slate-500 mb-2">Authenticated User</span>
              <button
                onClick={logout}
                className="w-full flex items-center justify-center gap-1.5 text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/30 hover:bg-red-100 dark:hover:bg-red-900/40 py-1.5 px-3 rounded-lg font-medium transition-colors"
              >
                <span className="material-symbols-outlined text-[16px]">logout</span>
                <span>Sign Out</span>
              </button>
            </div>
          </div>
        ) : (
          <Link
            href="/login"
            className="font-label-md text-label-md text-slate-700 dark:text-slate-300 hover:text-primary dark:hover:text-white font-medium transition-colors"
          >
            Sign In
          </Link>
        )}

        <a
          href="/dashboard"
          onClick={handleDashboardClick}
          className="bg-primary text-white px-lg py-sm rounded-lg font-label-md text-label-md hover:scale-95 transition-all duration-150 ease-in-out cursor-pointer"
        >
          Launch Dashboard
        </a>
      </div>
    </header>
  );
}
