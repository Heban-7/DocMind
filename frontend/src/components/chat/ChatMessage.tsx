"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { AnswerUsage, ChatMessageUI } from "@/lib/types";
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
            DocMind AI {message.usage?.model ? `(${message.usage.model})` : selectedModel ? `(${selectedModel})` : ""}
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

        {/* Answer footer: model, time, tokens, cost; the split on hover or focus */}
        {message.usage && <AnswerFooter usage={message.usage} notFound={message.status === "not_found"} />}

        {message.content && (
          <div className="flex items-center gap-md pt-xs">
            <button
              type="button"
              onClick={() => navigator.clipboard.writeText(message.content)}
              className="flex items-center gap-xs text-slate-400 dark:text-slate-500 hover:text-primary transition-colors"
              aria-label="Copy the answer"
              title="Copy the answer"
            >
              <span className="material-symbols-outlined text-sm" aria-hidden="true">content_copy</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

const STAGES: [string, string][] = [
  ["understand", "Reading the question"],
  ["retrieve", "Finding evidence"],
  ["answer", "Writing the answer"],
  ["check", "Checking numbers and boxes"],
];
const PURPOSES: Record<string, string> = { plan: "planning", embed: "search", answer: "answer", other: "other" };

function money(v: number): string {
  return v < 0.001 ? `$${v.toFixed(5)}` : `$${v.toFixed(4)}`;
}

function AnswerFooter({ usage, notFound }: { usage: AnswerUsage; notFound: boolean }) {
  const stages = usage.stages || {};
  const costs = usage.cost_by_purpose || {};
  const hasSplit = Object.keys(stages).length > 0 || Object.keys(costs).length > 0;
  return (
    <div className="relative group/footer inline-block">
      <p
        tabIndex={hasSplit ? 0 : undefined}
        className="text-[11px] text-slate-400 dark:text-slate-500 font-label-md outline-none focus:text-slate-600 dark:focus:text-slate-300"
      >
        {usage.model} · {usage.seconds.toFixed(1)} s
        {usage.first_token_s != null ? ` (first words ${usage.first_token_s.toFixed(1)} s)` : ""} ·{" "}
        {(usage.input_tokens + usage.output_tokens).toLocaleString()} tokens · {money(usage.cost_usd)}
        {notFound ? " · not found in the document" : ""}
      </p>
      {hasSplit && (
        <div
          role="tooltip"
          className="hidden group-hover/footer:block group-focus-within/footer:block absolute left-0 bottom-full mb-1 z-20 w-64 p-3 rounded-xl bg-white dark:bg-[#0c1021] border border-slate-200 dark:border-slate-800 shadow-xl text-[11px] text-slate-600 dark:text-slate-300"
        >
          {Object.keys(stages).length > 0 && (
            <table className="w-full mb-2">
              <tbody>
                {STAGES.filter(([k]) => stages[k] != null).map(([k, label]) => (
                  <tr key={k}>
                    <td className="py-0.5">{label}</td>
                    <td className="py-0.5 text-right tabular-nums">{stages[k].toFixed(2)} s</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {Object.keys(costs).length > 0 && (
            <table className="w-full border-t border-slate-200 dark:border-slate-800">
              <tbody>
                {Object.entries(costs).map(([k, v]) => (
                  <tr key={k}>
                    <td className="py-0.5">Cost, {PURPOSES[k] || k}</td>
                    <td className="py-0.5 text-right tabular-nums">{money(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="mt-1 text-slate-400">
            {usage.llm_calls} model call{usage.llm_calls === 1 ? "" : "s"}: {usage.input_tokens.toLocaleString()} in,{" "}
            {usage.output_tokens.toLocaleString()} out
          </p>
        </div>
      )}
    </div>
  );
}
