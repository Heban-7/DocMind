"use client";

import { useRef, useEffect, useState } from "react";
import DashboardSidebar from "@/components/layout/DashboardSidebar";
import DashboardHeader from "@/components/layout/DashboardHeader";
import ChatMessage from "@/components/chat/ChatMessage";
import ChatInput from "@/components/chat/ChatInput";
import WelcomeState from "@/components/chat/WelcomeState";
import { useChat } from "@/hooks/useChat";
import { useUpload } from "@/hooks/useUpload";

export default function DashboardPage() {
  const { messages, isLoading, send, newChat } = useChat();
  const { uploadState, document: uploadedDoc, upload } = useUpload();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [federatedSearch, setFederatedSearch] = useState(false);
  const [auditMode, setAuditMode] = useState(false);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = (text: string) => {
    send(text, uploadedDoc?.document_id);
  };

  return (
    <>
      {/* Sidebar */}
      <DashboardSidebar
        onNewChat={newChat}
        onUpload={upload}
        uploadState={uploadState}
        uploadedFileName={uploadedDoc?.file_name}
        strategyTier={uploadedDoc?.strategy_tier}
      />

      {/* Main Content Canvas */}
      <main className="flex-1 md:ml-[280px] h-screen flex flex-col bg-background relative">
        {/* Header */}
        <DashboardHeader
          federatedSearch={federatedSearch}
          onToggleFederated={() => setFederatedSearch((v) => !v)}
          auditMode={auditMode}
          onToggleAudit={() => setAuditMode((v) => !v)}
        />

        {/* Chat Workspace Area */}
        <section ref={scrollRef} className="flex-1 overflow-y-auto flex flex-col items-center">
          <div className="w-full max-w-[800px] px-lg py-xl flex-1 flex flex-col">
            {/* Welcome State (shown when no messages) */}
            {messages.length === 0 && (
              <WelcomeState onSuggestionClick={handleSend} />
            )}

            {/* Chat Messages */}
            <div className="space-y-xl pb-32">
              {messages.map((msg) => (
                <ChatMessage key={msg.id} message={msg} />
              ))}

              {/* Loading Indicator */}
              {isLoading && (
                <div className="flex flex-col items-start fade-in">
                  <div className="max-w-[90%] space-y-md">
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
                    <div className="flex items-center gap-sm text-on-surface-variant/50">
                      <span className="material-symbols-outlined text-sm animate-spin">
                        progress_activity
                      </span>
                      <span className="font-body-sm text-body-sm">Analyzing documents...</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </section>

        {/* Input Bar */}
        <ChatInput onSend={handleSend} isLoading={isLoading} />

        {/* Decorative Background Element */}
        <div className="fixed top-0 right-0 -z-10 w-1/3 h-1/3 opacity-20 pointer-events-none blur-[100px] bg-gradient-to-br from-primary to-secondary" />
      </main>
    </>
  );
}
