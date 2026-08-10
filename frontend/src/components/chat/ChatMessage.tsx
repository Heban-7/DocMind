"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessageUI } from "@/lib/types";
import ProvenanceBadge from "./ProvenanceBadge";

interface ChatMessageProps {
  message: ChatMessageUI;
  selectedModel?: string;
}

export default function ChatMessage({ message, selectedModel }: ChatMessageProps) {
  if (message.role === "user") {
    return (
      <div className="flex flex-col items-end fade-in">
        <div className="bg-primary/10 dark:bg-white/10 border border-primary/20 dark:border-white/10 px-lg py-md rounded-2xl rounded-tr-none max-w-[80%] shadow-sm">
          <p className="text-slate-900 dark:text-white whitespace-pre-wrap leading-relaxed">{message.content}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-start fade-in">
      <div className="max-w-[90%] space-y-md">
        {/* AI Header */}
        <div className="flex items-center gap-sm mb-xs">
          <div className="w-6 h-6 bg-primary rounded flex items-center justify-center shadow-sm">
            <span className="material-symbols-outlined text-white text-[16px]">
              auto_awesome
            </span>
          </div>
          <span className="font-label-md text-label-md font-bold text-primary dark:text-primary-fixed-dim">
            DocMind AI {selectedModel ? `(${selectedModel})` : ""}
          </span>
        </div>

        {/* AI Response Content or Analysis Loading Spinner */}
        <div className="text-slate-900 dark:text-slate-100 space-y-md leading-relaxed prose max-w-none">
          {!message.content ? (
            <div className="flex items-center gap-sm text-slate-400 dark:text-slate-500 py-1.5 fade-in">
              <span className="material-symbols-outlined text-sm animate-spin">
                progress_activity
              </span>
              <span className="font-body-sm text-body-sm font-medium">Analyzing documents...</span>
            </div>
          ) : (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                p: ({ children }) => <p className="mb-md last:mb-0 leading-relaxed text-slate-800 dark:text-slate-100">{children}</p>,
                ul: ({ children }) => <ul className="list-disc pl-lg space-y-xs my-md">{children}</ul>,
                ol: ({ children }) => <ol className="list-decimal pl-lg space-y-xs my-md">{children}</ol>,
                li: ({ children }) => <li className="text-slate-800 dark:text-slate-100">{children}</li>,
                h1: ({ children }) => <h1 className="font-headline-lg text-2xl font-bold my-md text-slate-900 dark:text-white">{children}</h1>,
                h2: ({ children }) => <h2 className="font-headline-md text-xl font-bold my-sm text-slate-900 dark:text-white">{children}</h2>,
                h3: ({ children }) => <h3 className="font-label-md text-base font-bold my-xs text-primary">{children}</h3>,
                code: ({ children }) => (
                  <code className="bg-slate-100 dark:bg-slate-800/80 px-1.5 py-0.5 rounded font-code text-xs text-primary dark:text-indigo-300 border border-slate-200 dark:border-slate-700">
                    {children}
                  </code>
                ),
                pre: ({ children }) => (
                  <pre className="bg-slate-100 dark:bg-[#070913] p-md rounded-xl font-code text-xs overflow-x-auto my-md border border-slate-200 dark:border-slate-800 shadow-sm text-slate-900 dark:text-slate-100">
                    {children}
                  </pre>
                ),
                table: ({ children }) => (
                  <div className="overflow-x-auto my-md">
                    <table className="w-full text-left border-collapse border border-slate-200 dark:border-slate-800 rounded-lg overflow-hidden">
                      {children}
                    </table>
                  </div>
                ),
                th: ({ children }) => (
                  <th className="bg-slate-100 dark:bg-slate-800/60 px-md py-sm font-label-md text-xs font-bold border-b border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white">
                    {children}
                  </th>
                ),
                td: ({ children }) => (
                  <td className="px-md py-sm border-b border-slate-200/60 dark:border-slate-800/60 text-body-sm font-body-sm text-slate-800 dark:text-slate-200">
                    {children}
                  </td>
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>
          )}

          {/* Provenance Badges — Structured in 2 Columns */}
          {message.provenance && message.provenance.length > 0 && (
            <div className="pt-2">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-full">
                {message.provenance.map((citation, i) => (
                  <ProvenanceBadge key={i} citation={citation} />
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Action Bar (shown when answer content exists) */}
        {message.content && (
          <div className="flex items-center gap-md pt-xs">
            <button className="flex items-center gap-xs text-slate-400 dark:text-slate-500 hover:text-primary transition-colors">
              <span className="material-symbols-outlined text-sm">thumb_up</span>
            </button>
            <button className="flex items-center gap-xs text-slate-400 dark:text-slate-500 hover:text-primary transition-colors">
              <span className="material-symbols-outlined text-sm">thumb_down</span>
            </button>
            <button
              onClick={() => navigator.clipboard.writeText(message.content)}
              className="flex items-center gap-xs text-slate-400 dark:text-slate-500 hover:text-primary transition-colors"
            >
              <span className="material-symbols-outlined text-sm">content_copy</span>
            </button>
            <button className="flex items-center gap-xs text-slate-400 dark:text-slate-500 hover:text-primary transition-colors">
              <span className="material-symbols-outlined text-sm">refresh</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
