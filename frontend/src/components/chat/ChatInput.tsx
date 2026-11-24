"use client";

import { useState, useRef, useCallback, useEffect } from "react";

import { fetchModels } from "@/lib/api";
import type { ModelCatalog, ModelInfo } from "@/lib/types";

function price(m: ModelInfo): string {
  const i = m.price.input_per_m, o = m.price.output_per_m;
  if (i == null || o == null) return "price not published";
  return `$${i} in / $${o} out per 1M tokens`;
}

interface ChatInputProps {
  onSend: (text: string, model: string) => void;
  isLoading: boolean;
  onAttachFile?: (file: File) => void;
  selectedModel?: string;
  onSelectModel?: (modelId: string) => void;
}

export default function ChatInput({
  onSend,
  isLoading,
  onAttachFile,
  selectedModel: externalModel,
  onSelectModel,
}: ChatInputProps) {
  const [text, setText] = useState("");
  const [currentModel, setCurrentModel] = useState(externalModel || "");
  const [catalog, setCatalog] = useState<ModelCatalog | null>(null);
  const [isOpenMenu, setIsOpenMenu] = useState(false);

  const menuRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Sync external model
  useEffect(() => {
    if (externalModel) setCurrentModel(externalModel);
  }, [externalModel]);

  // The models this server can run, with prices (empty model = the server default)
  useEffect(() => {
    fetchModels()
      .then((c) => {
        setCatalog(c);
        if (!externalModel && c.default) setCurrentModel(c.default);
      })
      .catch(() => setCatalog({ default: null, prices_checked_on: null, models: [] }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Click outside menu closer
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsOpenMenu(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const models = catalog?.models ?? [];
  const activeModelObj = models.find((m) => m.id === currentModel);
  const providers = Array.from(new Set(models.map((m) => m.provider)));

  const handleSelect = (modelId: string) => {
    setCurrentModel(modelId);
    onSelectModel?.(modelId);
    setIsOpenMenu(false);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && onAttachFile) {
      onAttachFile(file);
    }
  };

  const handleSubmit = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed, currentModel);
    setText("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "48px";
    }
  }, [text, isLoading, onSend, currentModel]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleInput = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "";
      textareaRef.current.style.height =
        textareaRef.current.scrollHeight + "px";
    }
  };


  return (
    <footer className="absolute bottom-0 left-0 w-full p-lg flex justify-center pointer-events-none z-30">
      <div className="w-full max-w-[800px] pointer-events-auto relative">
        {/* Model Selector Popover Menu */}
        {isOpenMenu && (
          <div
            ref={menuRef}
            className="absolute bottom-16 left-12 w-80 bg-surface-container-lowest dark:bg-[#0e1329] border border-outline-variant/30 dark:border-slate-800 rounded-2xl p-md shadow-2xl z-50 glass-card fade-in"
          >
            <div className="flex items-center justify-between pb-sm mb-sm border-b border-outline-variant/20">
              <span className="font-label-md text-xs uppercase font-bold text-on-surface-variant/70">
                Select Intelligence Model
              </span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-primary/10 text-primary font-bold">
                {models.filter((m) => m.available).length} available
              </span>
            </div>

            {providers.length === 0 && (
              <p className="text-[11px] text-on-surface-variant/70 px-sm">Using the server's default model.</p>
            )}
            {providers.map((provider) => (
              <div key={provider} className="mb-md last:mb-0">
                <span className="text-[11px] font-bold text-on-surface-variant/60 uppercase tracking-wider block px-sm mb-xs">
                  {provider}
                </span>
                <div className="space-y-xs">
                  {models
                    .filter((m) => m.provider === provider)
                    .map((m) => (
                      <button
                        key={m.id}
                        disabled={!m.available}
                        onClick={() => handleSelect(m.id)}
                        title={m.available ? m.data_use || "" : m.unavailable_reason || "not available"}
                        className={`w-full text-left p-xs px-sm rounded-xl transition-all flex items-center justify-between ${
                          currentModel === m.id
                            ? "bg-primary/10 text-primary font-bold"
                            : m.available
                              ? "hover:bg-surface-container text-on-surface hover:text-primary"
                              : "opacity-50 cursor-not-allowed text-on-surface"
                        }`}
                      >
                        <div>
                          <div className="flex items-center gap-xs">
                            <span className="font-label-md text-xs font-bold">{m.label}</span>
                            {m.default && (
                              <span className="text-[9px] px-1.5 py-0.2 rounded font-bold bg-emerald-500/10 text-emerald-600 border border-emerald-500/30">
                                Default
                              </span>
                            )}
                            {m.free_tier && (
                              <span className="text-[9px] px-1.5 py-0.2 rounded font-bold bg-surface-container-high text-on-surface-variant">
                                Free tier
                              </span>
                            )}
                          </div>
                          <p className="text-[10px] text-on-surface-variant/70 font-normal line-clamp-1">
                            {m.available ? price(m) : m.unavailable_reason}
                            {m.benchmark?.correct_pct != null ? ` · ${m.benchmark.correct_pct}% right on the test set` : ""}
                          </p>
                        </div>
                        {currentModel === m.id && (
                          <span className="material-symbols-outlined text-sm text-primary">check</span>
                        )}
                      </button>
                    ))}
                </div>
              </div>
            ))}
            {catalog?.prices_checked_on && (
              <p className="text-[10px] text-on-surface-variant/60 px-sm pt-xs">
                Prices checked {catalog.prices_checked_on}.
              </p>
            )}
          </div>
        )}

        {/* Input Bar Container */}
        <div className="relative bg-surface-container-lowest dark:bg-[#0c1021] shadow-lg border border-outline-variant/30 dark:border-slate-800 rounded-[2rem] p-sm pr-2 flex items-end gap-sm focus-within:ring-2 focus-within:ring-primary/20 transition-all">
          {/* Hidden File Input */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            className="hidden"
            onChange={handleFileChange}
          />

          {/* Attach File */}
          <button
            onClick={() => fileInputRef.current?.click()}
            className="p-2 text-slate-500 dark:text-slate-400 hover:text-primary dark:hover:text-white transition-colors rounded-full hover:bg-slate-200/50 dark:hover:bg-white/10"
            title="Attach & index PDF document"
          >
            <span className="material-symbols-outlined">attach_file</span>
          </button>

          {/* Interactive Model Selector Dropdown Button */}
          <button
            onClick={() => setIsOpenMenu((v) => !v)}
            className="flex items-center gap-xs px-2.5 py-1 text-slate-700 dark:text-slate-300 hover:text-primary dark:hover:text-white transition-colors rounded-lg hover:bg-slate-200/50 dark:hover:bg-white/10 border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800/60 shrink-0"
            title="Select AI Model"
          >
            <span className="material-symbols-outlined text-[16px] text-primary">smart_toy</span>
            <span className="font-label-md text-[12px] font-bold text-slate-900 dark:text-white">
              {activeModelObj?.label || "Default model"}
            </span>
            <span className="material-symbols-outlined text-[14px]">
              {isOpenMenu ? "expand_less" : "expand_more"}
            </span>
          </button>

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            className="flex-1 bg-transparent border-none focus:ring-0 focus:outline-none py-3 px-2 text-slate-900 dark:text-white placeholder:text-slate-400 dark:placeholder:text-slate-500 resize-none max-h-48 scrollbar-hide font-body-md"
            placeholder="Verify data or ask about indexed documents..."
            rows={1}
            style={{ height: "48px", overflowY: "hidden" }}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onInput={handleInput}
            onKeyDown={handleKeyDown}
          />


          {/* Send Button */}
          <button
            onClick={handleSubmit}
            disabled={isLoading || !text.trim()}
            className="bg-primary hover:bg-primary-container text-white w-10 h-10 rounded-full flex items-center justify-center transition-all scale-95 hover:scale-100 shadow-md disabled:opacity-40 disabled:hover:scale-95 shrink-0"
          >
            {isLoading ? (
              <span className="material-symbols-outlined text-[20px] animate-spin">
                progress_activity
              </span>
            ) : (
              <span className="material-symbols-outlined text-[20px] font-bold">
                arrow_upward
              </span>
            )}
          </button>
        </div>
        <p className="text-center text-[11px] text-on-surface-variant/40 mt-sm tracking-wide">
          DocMind AI can mistake data. Always cross-reference with provenance badges.
        </p>
      </div>
    </footer>
  );
}
