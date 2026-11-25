"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import {
  loginUser,
  registerUser,
  fetchMe,
  setStoredToken,
  getStoredToken,
  clearStoredToken,
} from "@/lib/api";
import type { UserProfile } from "@/lib/types";

interface AuthContextType {
  user: UserProfile | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [token, setToken] = useState<string | null>(null);
  // loading until the stored token is checked
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // On mount, check for existing token and validate it
  useEffect(() => {
    let live = true;
    const stored = getStoredToken();
    (stored ? fetchMe() : Promise.resolve(null))
      .then((profile) => {
        if (!live) return;
        setToken(profile ? stored : null);
        setUser(profile);
      })
      .catch(() => {
        if (!live) return;
        // the token expired or is invalid: clear it
        clearStoredToken();
        setToken(null);
        setUser(null);
      })
      .finally(() => {
        if (live) setIsLoading(false);
      });
    return () => {
      live = false;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setError(null);
    setIsLoading(true);
    try {
      const res = await loginUser(email, password);
      setStoredToken(res.access_token);
      setToken(res.access_token);
      const profile = await fetchMe();
      setUser(profile);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Login failed";
      setError(msg);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    setError(null);
    setIsLoading(true);
    try {
      await registerUser(email, password);
      // Auto-login after register
      const res = await loginUser(email, password);
      setStoredToken(res.access_token);
      setToken(res.access_token);
      const profile = await fetchMe();
      setUser(profile);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Registration failed";
      setError(msg);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    clearStoredToken();
    setToken(null);
    setUser(null);
    setError(null);
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!user && !!token,
        isLoading,
        error,
        login,
        register,
        logout,
        clearError,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
