import React from 'react';
import { ArrowLeft, Plus, MessageSquare, Settings, Trash2 } from 'lucide-react';
import type { Thread } from '../types';

interface ThreadSidebarProps {
  threads: Thread[];
  currentThreadId: string | null;
  onSelectThread: (id: string) => void;
  onNewThread: () => void;
  onGoHome: () => void;
  onDeleteThread: (id: string) => void;
  onOpenSettings: () => void;
  selectedProvider: string;
  selectedModel: string;
  onModelChange: (provider: string, model: string) => void;
}

const MODELS = [
  { provider: 'openai', name: 'gpt-4o', label: 'OpenAI: GPT-4o' },
  { provider: 'openai', name: 'gpt-4o-mini', label: 'OpenAI: GPT-4o-mini' },
  { provider: 'openai', name: 'gpt-5.4', label: 'OpenAI: GPT-5.4 (Experimental)' },
  { provider: 'openai', name: 'gpt-5.6-luna', label: 'OpenAI: GPT-5.6 Luna' },
  { provider: 'gemini', name: 'gemini-2.5-flash', label: 'Gemini: 2.5 Flash' },
  { provider: 'gemini', name: 'gemini-2.5-pro', label: 'Gemini: 2.5 Pro' },
  { provider: 'claude', name: 'claude-sonnet-4-5', label: 'Claude: Sonnet 4.5' },
  { provider: 'claude', name: 'claude-3-5-sonnet-20241022', label: 'Claude: 3.5 Sonnet' },
];

export const ThreadSidebar: React.FC<ThreadSidebarProps> = ({
  threads,
  currentThreadId,
  onSelectThread,
  onNewThread,
  onGoHome,
  onDeleteThread,
  onOpenSettings,
  selectedProvider,
  selectedModel,
  onModelChange,
}) => {
  return (
    <div className="w-64 bg-panel-dark border-r border-border-dark flex flex-col h-full">
      <div className="p-4 border-b border-border-dark flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-base font-bold bg-gradient-to-r from-accent-blue to-accent-indigo bg-clip-text text-transparent tracking-wide">
            🕵️ OSINT Agent
          </h1>
          <p className="text-xs text-slate-500 font-medium">Dashboard v2.0</p>
          <button
            onClick={onGoHome}
            className="mt-3 flex min-h-9 items-center gap-2 border border-border-dark px-2.5 text-[11px] font-semibold text-slate-400 transition-colors hover:border-accent-blue/50 hover:text-accent-blue"
            title="Back to investigation subjects"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Subjects
          </button>
        </div>
        <button onClick={onOpenSettings} className="p-1.5 rounded-none border border-border-dark text-slate-400 hover:border-accent-blue/50 hover:text-accent-blue" title="Open settings">
          <Settings className="w-4.5 h-4.5" />
        </button>
      </div>

      <div className="p-3 space-y-3">
        <button
          onClick={onNewThread}
          className="w-full py-2.5 px-4 bg-gradient-to-r from-accent-blue to-accent-indigo hover:opacity-90 text-white rounded-none text-sm font-semibold transition-transform active:scale-98 flex items-center justify-center gap-2 shadow-lg shadow-accent-blue/15"
        >
          <Plus className="w-4 h-4" />
          New Investigation
        </button>

        <div className="space-y-1.5 pt-1.5 border-t border-border-dark/40">
          <label className="text-[9px] text-slate-500 uppercase font-bold tracking-wider block">
            Active Brain (Benchmark)
          </label>
          <select
            value={`${selectedProvider}/${selectedModel}`}
            onChange={(e) => {
              const [p, m] = e.target.value.split('/');
              onModelChange(p, m);
            }}
            className="w-full text-[11px] bg-slate-950 border border-border-dark text-slate-300 p-2 focus:outline-none focus:border-accent-blue rounded-none font-mono cursor-pointer"
          >
            {MODELS.map((item) => (
              <option key={`${item.provider}/${item.name}`} value={`${item.provider}/${item.name}`}>
                {item.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2 space-y-1">
        <div className="px-2 py-1.5 text-slate-500 text-[10px] uppercase font-bold tracking-wider">
          Recent Threads
        </div>
        {threads.length === 0 ? (
          <div className="text-center text-xs text-slate-600 py-6">
            No history yet
          </div>
        ) : (
          threads.map((t) => {
            const isActive = t.thread_id === currentThreadId;
            return (
              <div
                key={t.thread_id}
                className={`group flex items-center justify-between px-3 py-2.5 rounded-none cursor-pointer transition-colors ${
                  isActive
                    ? 'bg-accent-blue/10 border border-accent-blue/20 text-slate-200'
                    : 'border border-transparent text-slate-400 hover:bg-slate-800/40 hover:text-slate-300'
                }`}
                onClick={() => onSelectThread(t.thread_id)}
              >
                <div className="flex items-start gap-2.5 overflow-hidden flex-1">
                  <MessageSquare className={`w-4 h-4 flex-shrink-0 mt-0.5 ${isActive ? 'text-accent-blue' : 'text-slate-500'}`} />
                  <div className="flex flex-col flex-1 overflow-hidden">
                    <span className="text-xs font-semibold truncate text-slate-300">
                      {t.title || 'New Investigation'}
                    </span>
                    <span className="text-[9px] text-slate-500 font-mono truncate" title={t.thread_id}>
                      {t.subject_name ? `${t.subject_name} · ` : ''}ID: {t.thread_id}
                    </span>
                  </div>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteThread(t.thread_id);
                  }}
                  className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-400 text-slate-500 rounded-none transition-opacity"
                  title="Delete Thread"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
