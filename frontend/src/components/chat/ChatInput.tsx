"use client";

import { useState, useRef, useCallback } from "react";

interface ChatInputProps {
  onSend: (text: string) => void;
  isLoading: boolean;
}

export default function ChatInput({ onSend, isLoading }: ChatInputProps) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setText("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "48px";
    }
  }, [text, isLoading, onSend]);

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
    <footer className="absolute bottom-0 left-0 w-full p-lg flex justify-center pointer-events-none">
      <div className="w-full max-w-[800px] pointer-events-auto">
        <div className="relative bg-surface-container-lowest shadow-lg border border-outline-variant/30 rounded-[2rem] p-sm pr-2 flex items-end gap-sm focus-within:ring-2 focus-within:ring-primary/20 transition-all">
          {/* Attach File */}
          <button className="p-2 text-on-surface-variant hover:text-primary transition-colors rounded-full hover:bg-surface-container">
            <span className="material-symbols-outlined">attach_file</span>
          </button>

          {/* Model Selector */}
          <button className="flex items-center gap-xs px-2 py-1 text-on-surface-variant hover:text-primary transition-colors rounded-md hover:bg-surface-container border border-transparent hover:border-outline-variant/30">
            <span className="material-symbols-outlined text-[18px]">smart_toy</span>
            <span className="font-label-md text-[12px] font-bold">Pro</span>
            <span className="material-symbols-outlined text-[14px]">expand_more</span>
          </button>

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            className="flex-1 bg-transparent border-none focus:ring-0 focus:outline-none py-3 px-2 text-on-surface placeholder:text-on-surface-variant/50 resize-none max-h-48 scrollbar-hide font-body-md"
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
            className="bg-primary hover:bg-primary-container text-white w-10 h-10 rounded-full flex items-center justify-center transition-all scale-95 hover:scale-100 shadow-md disabled:opacity-40 disabled:hover:scale-95"
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
