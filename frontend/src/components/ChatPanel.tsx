import React, { useRef, useEffect } from 'react';
import { Send, Terminal, ChevronDown, User } from 'lucide-react';
import type { Message } from '../types';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface GroupedMessage {
  id: string;
  role: 'user' | 'assistant';
  content?: string;
  items?: Array<
    | { type: 'text'; content: string }
    | { type: 'tool'; name: string; args: any; result?: string }
  >;
  metrics?: any;
}

const groupMessages = (msgs: Message[]): GroupedMessage[] => {
  const grouped: GroupedMessage[] = [];
  let currentAssistantTurn: GroupedMessage | null = null;

  for (const m of msgs) {
    if (m.role === 'system') continue;

    if (m.role === 'user') {
      currentAssistantTurn = null;
      grouped.push({
        id: Math.random().toString(),
        role: 'user',
        content: m.content,
      });
    } else {
      if (!currentAssistantTurn) {
        currentAssistantTurn = {
          id: Math.random().toString(),
          role: 'assistant',
          items: [],
        };
        grouped.push(currentAssistantTurn);
      }

      if (m.metrics) {
        currentAssistantTurn.metrics = m.metrics;
      }

      if (m.isToolCall || m.role === 'tool') {
        currentAssistantTurn.items?.push({
          type: 'tool',
          name: m.toolName || 'tool',
          args: m.toolArgs,
          result: m.toolResult,
        });
      } else if (m.content && m.content.trim()) {
        currentAssistantTurn.items?.push({
          type: 'text',
          content: m.content,
        });
      }
    }
  }

  return grouped;
};

interface ChatPanelProps {
  messages: Message[];
  inputValue: string;
  setInputValue: (val: string) => void;
  onSendMessage: () => void;
  isLoading: boolean;
  activeTool: { name: string; args: any; result?: string } | null;
}

export const ChatPanel: React.FC<ChatPanelProps> = ({
  messages,
  inputValue,
  setInputValue,
  onSendMessage,
  isLoading,
  activeTool,
}) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, activeTool]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSendMessage();
    }
  };

  return (
    <div className="flex-1 flex flex-col bg-bg-dark h-full overflow-hidden">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && !activeTool ? (
          <div className="h-full flex flex-col items-center justify-center text-slate-500 text-sm gap-2">
            <span className="text-4xl">🔍</span>
            <h2 className="font-semibold text-slate-400">Start an OSINT Investigation</h2>
            <p className="text-xs text-slate-600">Enter a target name, email, or domain to begin.</p>
          </div>
        ) : (
          groupMessages(messages).map((m) => {
            const isUser = m.role === 'user';
            
            if (isUser) {
              return (
                <div
                  key={m.id}
                  className="flex gap-3 max-w-3xl w-full animate-fade-in ml-auto flex-row-reverse"
                >
                  <div className="w-8 h-8 rounded-none flex items-center justify-center text-xs flex-shrink-0 border bg-gradient-to-tr from-accent-blue to-accent-indigo border-accent-indigo text-white">
                    <User className="w-4 h-4" />
                  </div>
                  <div className="px-4 py-3 rounded-none text-sm leading-relaxed max-w-xl border bg-accent-blue/10 border-accent-blue/20 text-slate-200">
                    <div className="whitespace-pre-wrap">{m.content}</div>
                  </div>
                </div>
              );
            }

            return (
              <div
                key={m.id}
                className="flex gap-3 max-w-3xl w-full animate-fade-in mr-auto"
              >
                <div className="w-8 h-8 rounded-none flex items-center justify-center text-xs flex-shrink-0 border bg-slate-900 border-border-dark text-slate-400 animate-fade-in">
                  🤖
                </div>
                <div className="px-4 py-3 rounded-none text-sm leading-relaxed max-w-xl border bg-panel-dark border-border-dark text-slate-300 w-full space-y-3.5 animate-fade-in">
                  {m.items?.map((item, idx) => {
                    if (item.type === 'text') {
                      return (
                        <div key={idx} className="text-sm text-slate-300">
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                              h1: ({ node, ...props }) => <h1 className="text-sm font-bold mt-2.5 mb-1.5 text-accent-blue border-b border-border-dark/30 pb-0.5" {...props} />,
                              h2: ({ node, ...props }) => <h2 className="text-xs font-bold mt-2 mb-1 text-accent-indigo" {...props} />,
                              h3: ({ node, ...props }) => <h3 className="text-[11px] font-semibold mt-1.5 mb-0.5 text-slate-200" {...props} />,
                              p: ({ node, ...props }) => <p className="mb-1.5 last:mb-0" {...props} />,
                              ul: ({ node, ...props }) => <ul className="list-disc pl-4 mb-1.5 space-y-0.5" {...props} />,
                              ol: ({ node, ...props }) => <ol className="list-decimal pl-4 mb-1.5 space-y-0.5" {...props} />,
                              li: ({ node, ...props }) => <li className="text-slate-300" {...props} />,
                              code: ({ node, className, children, ...props }: any) => {
                                const match = /language-(\w+)/.exec(className || '');
                                const isInline = !match;
                                return isInline ? (
                                  <code className="bg-slate-950 px-1 py-0.5 font-mono text-[10px] text-accent-indigo border border-border-dark/40" {...props}>
                                    {children}
                                  </code>
                                ) : (
                                  <pre className="bg-slate-950 p-2 border border-border-dark overflow-x-auto my-1.5 text-[10px] font-mono text-slate-400 w-full">
                                    <code className={className} {...props}>{children}</code>
                                  </pre>
                                );
                              },
                              a: ({ node, ...props }) => <a className="text-accent-blue hover:underline font-semibold" target="_blank" rel="noreferrer" {...props} />,
                              blockquote: ({ node, ...props }) => <blockquote className="border-l-2 border-accent-blue/40 pl-3 italic text-slate-400 my-1.5" {...props} />,
                              table: ({ node, ...props }) => (
                                <div className="overflow-x-auto my-3 border border-border-dark w-full">
                                  <table className="min-w-full divide-y divide-border-dark text-[10px] font-mono border-collapse" {...props} />
                                </div>
                              ),
                              thead: ({ node, ...props }) => <thead className="bg-slate-900/60" {...props} />,
                              tbody: ({ node, ...props }) => <tbody className="divide-y divide-border-dark/30 bg-slate-950/20" {...props} />,
                              tr: ({ node, ...props }) => <tr className="hover:bg-slate-900/20 transition-colors" {...props} />,
                              th: ({ node, ...props }) => <th className="px-3 py-1.5 text-left font-bold text-slate-400 border-r border-border-dark/40 last:border-r-0" {...props} />,
                              td: ({ node, ...props }) => <td className="px-3 py-1.5 text-slate-300 border-r border-border-dark/30 last:border-r-0 break-words" {...props} />,
                            }}
                          >
                            {item.content}
                          </ReactMarkdown>
                        </div>
                      );
                    } else {
                      return (
                        <div key={idx} className="max-w-2xl bg-panel-dark/40 border border-border-dark/65 text-xs font-mono my-2 w-full">
                          <details className="group" open={!item.result}>
                            <summary className="flex items-center gap-2 p-2 bg-panel-dark/85 cursor-pointer select-none border-b border-border-dark/30">
                              <Terminal className={`w-3.5 h-3.5 ${item.result ? 'text-accent-blue' : 'text-yellow-500 animate-pulse'}`} />
                              <span className="font-semibold text-slate-300 text-[11px]">
                                {item.result ? '⚙' : '⚡'} Executed: {item.name}
                              </span>
                              <ChevronDown className="w-3.5 h-3.5 ml-auto text-slate-500 transition-transform group-open:rotate-180" />
                            </summary>
                            <div className="p-3 space-y-2 bg-slate-950/20 text-slate-400 border-t border-border-dark">
                              {item.args && (
                                <div>
                                  <div className="text-[10px] text-slate-500 mb-0.5">Arguments:</div>
                                  <pre className="overflow-x-auto bg-slate-900/50 p-2 rounded-none text-[10px]">
                                    {JSON.stringify(item.args, null, 2)}
                                  </pre>
                                </div>
                              )}
                              <div>
                                <div className="text-[10px] text-slate-500 mb-0.5">Result:</div>
                                <pre className="overflow-x-auto bg-slate-900/50 p-2 rounded-none text-[10px] whitespace-pre-wrap max-h-40 overflow-y-auto font-mono text-[10px] text-slate-400">
                                  {item.result || '(running...)'}
                                </pre>
                              </div>
                            </div>
                          </details>
                        </div>
                      );
                    }
                  })}
                  
                  {m.metrics && (
                    <div className="mt-2 pt-1.5 border-t border-border-dark/30 flex items-center gap-3 text-[9px] text-slate-500 font-mono">
                      <span>⏱️ Latency: {m.metrics.duration_sec}s</span>
                      <span>🔄 Steps: {m.metrics.iterations}</span>
                      <span>⚙️ Tools: {m.metrics.tools_called}</span>
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}

        {/* Collapsible active tool call if agent is running */}
        {activeTool && (
          <div className="max-w-2xl bg-panel-dark/60 border border-border-dark rounded-none overflow-hidden text-xs font-mono">
            <details className="group">
              <summary className="flex items-center gap-2 p-3 bg-panel-dark border-b border-border-dark/60 cursor-pointer select-none">
                <Terminal className="w-3.5 h-3.5 text-yellow-500 animate-pulse" />
                <span className="font-semibold text-slate-200">Executing: {activeTool.name}</span>
                <ChevronDown className="w-3.5 h-3.5 ml-auto text-slate-500 transition-transform group-open:rotate-180" />
              </summary>
              <div className="p-3 space-y-2 bg-slate-950/40 text-slate-400">
                <div>
                  <div className="font-semibold text-slate-500 mb-0.5">Arguments:</div>
                  <pre className="overflow-x-auto text-[10px] bg-slate-900/50 p-2 rounded-none">
                    {JSON.stringify(activeTool.args, null, 2)}
                  </pre>
                </div>
                {activeTool.result && (
                  <div>
                    <div className="font-semibold text-slate-500 mb-0.5">Result (truncated):</div>
                    <pre className="overflow-x-auto text-[10px] bg-slate-900/50 p-2 rounded-none whitespace-pre-wrap max-h-40 overflow-y-auto">
                      {activeTool.result}
                    </pre>
                  </div>
                )}
              </div>
            </details>
          </div>
        )}

        {isLoading && !activeTool && (
          <div className="flex gap-3 mr-auto">
            <div className="w-8 h-8 rounded-none bg-slate-900 border border-border-dark flex items-center justify-center text-xs flex-shrink-0 text-slate-400">
              🤖
            </div>
            <div className="px-4 py-3 bg-panel-dark border border-border-dark rounded-none flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-none bg-accent-blue animate-bounce" style={{ animationDelay: '0ms' }} />
              <div className="w-1.5 h-1.5 rounded-none bg-accent-blue animate-bounce" style={{ animationDelay: '150ms' }} />
              <div className="w-1.5 h-1.5 rounded-none bg-accent-blue animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="p-4 border-t border-border-dark bg-panel-dark">
        <div className="flex gap-3 items-end bg-slate-950 p-2.5 rounded-none border border-border-dark focus-within:border-accent-blue transition-colors">
          <textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isLoading ? "Agent is investigating..." : "Ask the OSINT agent..."}
            disabled={isLoading}
            rows={1}
            className="flex-1 bg-transparent border-none outline-none resize-none text-slate-200 text-sm py-1.5 max-h-32 leading-relaxed"
          />
          <button
            onClick={onSendMessage}
            disabled={isLoading || !inputValue.trim()}
            className="p-2 bg-gradient-to-r from-accent-blue to-accent-indigo hover:opacity-90 disabled:opacity-30 disabled:cursor-not-allowed rounded-none text-white transition-all active:scale-95 flex-shrink-0"
          >
            <Send className="w-4.5 h-4.5" />
          </button>
        </div>
        <div className="text-[10px] text-slate-500 mt-2 text-center">
          Press Enter to send · Shift+Enter for newline
        </div>
      </div>
    </div>
  );
};
