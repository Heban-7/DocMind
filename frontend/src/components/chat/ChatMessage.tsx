"use client";

import type { ChatMessageUI } from "@/lib/types";
import ProvenanceBadge from "./ProvenanceBadge";

interface ChatMessageProps {
  message: ChatMessageUI;
}

export default function ChatMessage({ message }: ChatMessageProps) {
  if (message.role === "user") {
    return (
      <div className="flex flex-col items-end fade-in">
        <div className="bg-surface-container-high px-lg py-md rounded-2xl rounded-tr-none max-w-[80%]">
          <p className="text-on-surface">{message.content}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-start fade-in">
      <div className="max-w-[90%] space-y-md">
        {/* AI Header */}
        <div className="flex items-center gap-sm mb-xs">
          <div className="w-6 h-6 bg-primary rounded flex items-center justify-center">
            <span className="material-symbols-outlined text-white text-[16px]">
              auto_awesome
            </span>
          </div>
          <span className="font-label-md text-label-md font-bold text-primary">
            DocMind AI
          </span>
        </div>

        {/* AI Response Content */}
        <div className="text-on-surface space-y-md leading-relaxed">
          {message.content.split("\n\n").map((paragraph, i) => (
            <p key={i} dangerouslySetInnerHTML={{ __html: formatBold(paragraph) }} />
          ))}

          {/* Provenance Badges */}
          {message.provenance && message.provenance.length > 0 && (
            <div className="pt-sm flex flex-wrap gap-sm">
              {message.provenance.map((citation, i) => (
                <ProvenanceBadge key={i} citation={citation} />
              ))}
            </div>
          )}
        </div>

        {/* Action Bar */}
        <div className="flex items-center gap-md pt-xs">
          <button className="flex items-center gap-xs text-on-surface-variant/50 hover:text-primary transition-colors">
            <span className="material-symbols-outlined text-sm">thumb_up</span>
          </button>
          <button className="flex items-center gap-xs text-on-surface-variant/50 hover:text-primary transition-colors">
            <span className="material-symbols-outlined text-sm">thumb_down</span>
          </button>
          <button
            onClick={() => navigator.clipboard.writeText(message.content)}
            className="flex items-center gap-xs text-on-surface-variant/50 hover:text-primary transition-colors"
          >
            <span className="material-symbols-outlined text-sm">content_copy</span>
          </button>
          <button className="flex items-center gap-xs text-on-surface-variant/50 hover:text-primary transition-colors">
            <span className="material-symbols-outlined text-sm">refresh</span>
          </button>
        </div>
      </div>
    </div>
  );
}

/** Simple bold formatting: wraps **text** in <strong> tags */
function formatBold(text: string): string {
  return text.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
}
