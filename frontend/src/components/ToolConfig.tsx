import React, { useEffect, useState } from 'react';
import { ToggleLeft, ToggleRight, Loader } from 'lucide-react';
import type { ToolInfo } from '../types';

interface ToolConfigProps {
  onRefreshToolsTrigger: number;
}

export const ToolConfig: React.FC<ToolConfigProps> = ({ onRefreshToolsTrigger }) => {
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchTools = async () => {
    try {
      const res = await fetch('/api/tools');
      const data = await res.json();
      setTools(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTools();
  }, [onRefreshToolsTrigger]);

  const toggleTool = async (name: string, currentEnabled: boolean) => {
    try {
      // Optimistic update
      setTools((prev) =>
        prev.map((t) => (t.name === name ? { ...t, enabled: !currentEnabled } : t))
      );
      await fetch(`/api/tools/${name}/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !currentEnabled }),
      });
    } catch (e) {
      console.error(e);
      // Revert if error
      fetchTools();
    }
  };

  if (loading) {
    return (
      <div className="p-4 border-b border-border-dark flex items-center justify-center text-slate-500 text-xs">
        <Loader className="animate-spin w-4 h-4 mr-2" />
        Loading Tools Config...
      </div>
    );
  }

  return (
    <div className="bg-panel-dark/40 border-b border-border-dark p-4">
      <div className="text-xs font-semibold text-slate-400 mb-3 uppercase tracking-wider flex items-center justify-between">
        <span>OSINT Core Tools</span>
        <span className="text-[10px] text-slate-500">Enable/disable features</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
        {tools.map((t) => (
          <div
            key={t.name}
            onClick={() => toggleTool(t.name, t.enabled)}
            className={`flex items-center justify-between px-3 py-2.5 rounded-none border cursor-pointer transition-colors ${
              t.enabled
                ? 'bg-accent-blue/10 border-accent-blue/40 text-slate-100'
                : 'bg-slate-900/40 border-border-dark text-slate-400 hover:border-slate-700 hover:text-slate-300'
            }`}
          >
            <div className="overflow-hidden mr-2">
              <div className={`text-xs font-semibold truncate leading-none mb-1 uppercase tracking-wide ${
                t.enabled ? 'text-accent-blue font-bold' : 'text-slate-300'
              }`}>
                {t.name.replace(/_tool|tool_/gi, '').replace(/_/g, ' ')}
              </div>
              <span className={`text-[9px] font-mono truncate block ${
                t.enabled ? 'text-accent-blue/60' : 'text-slate-500'
              }`}>
                {t.name}
              </span>
            </div>
            <button className="flex-shrink-0 focus:outline-none">
              {t.enabled ? (
                <ToggleRight className="w-6 h-6 text-accent-blue" />
              ) : (
                <ToggleLeft className="w-6 h-6 text-slate-700" />
              )}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};
