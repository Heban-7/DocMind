"use client";

import { useCallback, useRef, useState } from "react";

import ModelPicker from "./ModelPicker";

interface ChatInputProps {
  onSend: (text: string, model: string) => void;
  isLoading: boolean;
  onAttachFile?: (file: File) => void;
  selectedModel?: string;
  onSelectModel?: (modelId: string) => void;
}

export default function ChatInput({ onSend, isLoading, onAttachFile, selectedModel = "", onSelectModel }: ChatInputProps) {
  const [text, setText] = useState("");
  const [model, setModel] = useState(selectedModel);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const current = selectedModel || model;

  const choose = (id: string) => {
    setModel(id);
    onSelectModel?.(id);
  };

  const handleSubmit = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed, current);
    setText("");
    if (textareaRef.current) textareaRef.current.style.height = "48px";
  }, [text, isLoading, onSend, current]);

  return (
    <footer className="absolute bottom-0 left-0 w-full p-lg flex justify-center pointer-events-none z-30">
      <div className="w-full max-w-[800px] pointer-events-auto relative">
        <div className="relative bg-surface-container-lowest dark:bg-[#0c1021] shadow-lg border border-outline-variant/30 dark:border-slate-800 rounded-[2rem] p-sm pr-2 flex items-end gap-sm focus-within:ring-2 focus-within:ring-primary/20 transition-all">
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            className="hidden"
            aria-hidden="true"
            tabIndex={-1}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file && onAttachFile) onAttachFile(file);
              e.target.value = "";
            }}
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="p-2 text-slate-500 dark:text-slate-400 hover:text-primary dark:hover:text-white transition-colors rounded-full hover:bg-slate-200/50 dark:hover:bg-white/10"
            aria-label="Upload a PDF"
            title="Upload a PDF"
          >
            <span className="material-symbols-outlined" aria-hidden="true">attach_file</span>
          </button>

          <ModelPicker value={current} onChange={choose} />

          <textarea
            ref={textareaRef}
            aria-label="Your question"
            className="flex-1 bg-transparent border-none focus:ring-0 focus:outline-none py-3 px-2 text-slate-900 dark:text-white placeholder:text-slate-400 dark:placeholder:text-slate-500 resize-none max-h-48 scrollbar-hide font-body-md"
            placeholder="Ask about your documents, or check a figure…"
            rows={1}
            style={{ height: "48px", overflowY: "hidden" }}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onInput={() => {
              const el = textareaRef.current;
              if (el) {
                el.style.height = "";
                el.style.height = el.scrollHeight + "px";
              }
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSubmit();
              }
            }}
          />

          <button
            type="button"
            onClick={handleSubmit}
            disabled={isLoading || !text.trim()}
            aria-label={isLoading ? "Answering" : "Send"}
            className="bg-primary hover:bg-primary-container text-white w-10 h-10 rounded-full flex items-center justify-center transition-all scale-95 hover:scale-100 shadow-md disabled:opacity-40 disabled:hover:scale-95 shrink-0"
          >
            <span className={`material-symbols-outlined text-[20px] ${isLoading ? "animate-spin" : "font-bold"}`} aria-hidden="true">
              {isLoading ? "progress_activity" : "arrow_upward"}
            </span>
          </button>
        </div>
        <p className="text-center text-[11px] text-on-surface-variant/50 mt-sm tracking-wide">
          Every number in an answer is checked against its evidence, but a page can be misread: open the citations to see the source.
        </p>
      </div>
    </footer>
  );
}
