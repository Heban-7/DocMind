"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
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
          <p className="text-on-surface whitespace-pre-wrap">{message.content}</p>
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
        <div className="text-on-surface space-y-md leading-relaxed prose prose-indigo max-w-none">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              p: ({ children }) => <p className="mb-md last:mb-0 leading-relaxed">{children}</p>,
              ul: ({ children }) => <ul className="list-disc pl-lg space-y-xs my-md">{children}</ul>,
              ol: ({ children }) => <ol className="list-decimal pl-lg space-y-xs my-md">{children}</ol>,
              li: ({ children }) => <li className="text-on-surface">{children}</li>,
              h1: ({ children }) => <h1 className="font-headline-lg text-headline-lg font-bold my-md text-on-surface">{children}</h1>,
              h2: ({ children }) => <h2 className="font-headline-md text-headline-md font-bold my-sm text-on-surface">{children}</h2>,
              h3: ({ children }) => <h3 className="font-label-md text-label-md font-bold my-xs text-primary">{children}</h3>,
              code: ({ children }) => (
                <code className="bg-surface-container px-1.5 py-0.5 rounded font-code text-xs text-primary">
                  {children}
                </code>
              ),
              pre: ({ children }) => (
                <pre className="bg-surface-container-high p-md rounded-xl font-code text-xs overflow-x-auto my-md border border-outline-variant/30">
                  {children}
                </pre>
              ),
              table: ({ children }) => (
                <div className="overflow-x-auto my-md">
                  <table className="w-full text-left border-collapse border border-outline-variant/30 rounded-lg overflow-hidden">
                    {children}
                  </table>
                </div>
              ),
              th: ({ children }) => (
                <th className="bg-surface-container px-md py-sm font-label-md text-xs font-bold border-b border-outline-variant/30 text-on-surface">
                  {children}
                </th>
              ),
              td: ({ children }) => (
                <td className="px-md py-sm border-b border-outline-variant/20 text-body-sm font-body-sm text-on-surface">
                  {children}
                </td>
              ),
            }}
          >
            {message.content}
          </ReactMarkdown>

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

