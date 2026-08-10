"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Navbar from "@/components/layout/Navbar";
import Footer from "@/components/layout/Footer";
import Image from "next/image";
import { useAuth } from "@/context/AuthContext";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirectTarget = searchParams?.get("redirect") || "/dashboard";

  const { login, register, isLoading: authLoading, error: authError, clearError, isAuthenticated } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isRegisterMode, setIsRegisterMode] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (isAuthenticated) {
      router.replace(redirectTarget);
    }
  }, [isAuthenticated, router, redirectTarget]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    clearError();
    setIsSubmitting(true);
    try {
      if (isRegisterMode) {
        await register(email, password);
      } else {
        await login(email, password);
      }
      router.push(redirectTarget);
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setIsSubmitting(false);
    }
  };

  const displayError = localError || authError;

  return (
    <div className="w-full max-w-[440px] bg-white dark:bg-[#0c1021] border border-slate-200 dark:border-slate-800 rounded-2xl p-8 sm:p-10 shadow-2xl relative z-10 fade-in">
      {/* Header */}
      <div className="text-center mb-8">
        <div className="w-12 h-12 rounded-2xl overflow-hidden mx-auto mb-4 shadow-sm border border-primary/20">
          <Image
            src="/logo.jpg"
            alt="DocMind Logo"
            width={48}
            height={48}
            className="w-full h-full object-cover"
          />
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold text-slate-900 dark:text-white tracking-tight mb-2">
          {isRegisterMode ? "Create Account" : "Sign In to DocMind"}
        </h1>

        <p className="text-sm text-slate-600 dark:text-slate-400">
          Enterprise Document Intelligence Refinery
        </p>
      </div>

      {/* Error Banner */}
      {displayError && (
        <div className="mb-6 p-3 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/40 text-sm text-red-700 dark:text-red-300 flex items-center gap-2">
          <span className="material-symbols-outlined text-[18px]">error</span>
          <span>{displayError}</span>
        </div>
      )}

      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1.5">
            Email Address
          </label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="name@company.com"
            autoComplete="email"
            className="w-full bg-slate-50 dark:bg-slate-900/80 border border-slate-300 dark:border-slate-700/80 rounded-xl px-4 py-3 text-sm text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/40 transition-all"
          />
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1.5">
            Password
          </label>
          <input
            type="password"
            required
            minLength={6}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            autoComplete={isRegisterMode ? "new-password" : "current-password"}
            className="w-full bg-slate-50 dark:bg-slate-900/80 border border-slate-300 dark:border-slate-700/80 rounded-xl px-4 py-3 text-sm text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/40 transition-all"
          />
        </div>

        <button
          type="submit"
          disabled={isSubmitting || authLoading}
          className="w-full bg-primary hover:bg-primary/90 text-white py-3.5 px-4 rounded-xl font-bold text-sm transition-all shadow-md active:scale-[0.98] disabled:opacity-50 mt-2"
        >
          {isSubmitting
            ? (isRegisterMode ? "Creating Account..." : "Signing In...")
            : (isRegisterMode ? "Create Account" : "Sign In to DocMind")}
        </button>
      </form>

      {/* Toggle Register / Login */}
      <div className="relative flex items-center justify-center my-6">
        <div className="w-full border-t border-slate-200 dark:border-slate-800" />
      </div>

      <p className="text-center text-sm text-slate-600 dark:text-slate-400">
        {isRegisterMode ? (
          <>
            Already have an account?{" "}
            <button
              onClick={() => { setIsRegisterMode(false); setLocalError(null); clearError(); }}
              className="text-primary font-bold hover:underline"
            >
              Sign In
            </button>
          </>
        ) : (
          <>
            Don&apos;t have an account?{" "}
            <button
              onClick={() => { setIsRegisterMode(true); setLocalError(null); clearError(); }}
              className="text-primary font-bold hover:underline"
            >
              Create Account
            </button>
          </>
        )}
      </p>
    </div>
  );
}

export default function LoginPage() {
  return (
    <>
      <Navbar />

      <main className="min-h-screen pt-24 pb-16 px-4 flex items-center justify-center relative bg-slate-50 dark:bg-[#03050f] transition-colors duration-300">
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-primary/10 rounded-full blur-[140px] pointer-events-none -z-0" />
        <Suspense fallback={
          <div className="text-slate-500 flex items-center gap-2">
            <span className="material-symbols-outlined animate-spin">progress_activity</span>
            <span>Loading authentication form...</span>
          </div>
        }>
          <LoginForm />
        </Suspense>
      </main>

      <Footer />
    </>
  );
}
