import React, { useEffect, useState } from 'react';
import { Database, Network, RefreshCw, Layers } from 'lucide-react';
import type { KBEntity, KBEdge } from '../types';

interface KBViewerProps {
  threadId: string | null;
  refreshTrigger: number;
}

const LABEL_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  PERSON: { bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/20' },
  ORGANIZATION: { bg: 'bg-blue-500/10', text: 'text-blue-400', border: 'border-blue-500/20' },
  LOCATION: { bg: 'bg-green-500/10', text: 'text-green-400', border: 'border-green-500/20' },
  EMAIL: { bg: 'bg-yellow-500/10', text: 'text-yellow-400', border: 'border-yellow-500/20' },
  PHONE: { bg: 'bg-purple-500/10', text: 'text-purple-400', border: 'border-purple-500/20' },
  DOMAIN: { bg: 'bg-cyan-500/10', text: 'text-cyan-400', border: 'border-cyan-500/20' },
  IP_ADDRESS: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/20' },
  IMAGE: { bg: 'bg-pink-500/10', text: 'text-pink-400', border: 'border-pink-500/20' },
  DEFAULT: { bg: 'bg-slate-500/10', text: 'text-slate-400', border: 'border-slate-500/20' },
};

export const KBViewer: React.FC<KBViewerProps> = ({ threadId, refreshTrigger }) => {
  const [activeTab, setActiveTab] = useState<'entities' | 'relations'>('entities');
  const [entities, setEntities] = useState<KBEntity[]>([]);
  const [edges, setEdges] = useState<KBEdge[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchKB = async () => {
    if (!threadId) {
      setEntities([]);
      setEdges([]);
      return;
    }
    setLoading(true);
    try {
      const [entRes, edgeRes] = await Promise.all([
        fetch(`/api/kb/${threadId}/entities`),
        fetch(`/api/kb/${threadId}/edges`),
      ]);
      if (entRes.ok) {
        const entData = await entRes.json();
        // The API returns either raw array or { entities: [...] }
        setEntities(Array.isArray(entData) ? entData : entData.entities || []);
      }
      if (edgeRes.ok) {
        const edgeData = await edgeRes.json();
        setEdges(Array.isArray(edgeData) ? edgeData : edgeData.edges || []);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchKB();
  }, [threadId, refreshTrigger]);

  if (!threadId) {
    return (
      <div className="w-80 bg-panel-dark border-l border-border-dark flex flex-col items-center justify-center p-6 text-center text-slate-500 text-xs">
        <Network className="w-10 h-10 mb-3 text-slate-700 stroke-[1.5]" />
        Select a thread to view extracted Knowledge Graph entities and relationships.
      </div>
    );
  }

  return (
    <div className="w-80 bg-panel-dark border-l border-border-dark flex flex-col h-full overflow-hidden">
      <div className="p-4 border-b border-border-dark flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Database className="w-4 h-4 text-accent-blue" />
          <h2 className="text-sm font-semibold text-slate-200">Knowledge Base</h2>
        </div>
        <button
          onClick={fetchKB}
          disabled={loading}
          className="p-1 text-slate-400 hover:text-slate-200 transition-colors disabled:opacity-50"
          title="Refresh Graph"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="flex border-b border-border-dark bg-slate-950/40 p-1 m-2 rounded-none">
        <button
          onClick={() => setActiveTab('entities')}
          className={`flex-1 py-1.5 text-xs font-semibold rounded-none transition-colors flex items-center justify-center gap-1.5 ${
            activeTab === 'entities'
              ? 'bg-accent-blue/15 text-accent-blue'
              : 'text-slate-400 hover:text-slate-300'
          }`}
        >
          <Layers className="w-3.5 h-3.5" />
          Entities ({entities.length})
        </button>
        <button
          onClick={() => setActiveTab('relations')}
          className={`flex-1 py-1.5 text-xs font-semibold rounded-none transition-colors flex items-center justify-center gap-1.5 ${
            activeTab === 'relations'
              ? 'bg-accent-blue/15 text-accent-blue'
              : 'text-slate-400 hover:text-slate-300'
          }`}
        >
          <Network className="w-3.5 h-3.5" />
          Edges ({edges.length})
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {loading && (
          <div className="flex items-center justify-center py-12 text-slate-500 text-xs">
            <RefreshCw className="animate-spin w-4 h-4 mr-2" />
            Updating graph view...
          </div>
        )}

        {!loading && activeTab === 'entities' && (
          <div className="space-y-2">
            {entities.length === 0 ? (
              <div className="text-center text-xs text-slate-600 py-12">
                No entities extracted yet.
              </div>
            ) : (
              entities.map((e, idx) => {
                const colors = LABEL_COLORS[e.label.toUpperCase()] || LABEL_COLORS.DEFAULT;
                return (
                  <div
                    key={e.id || idx}
                    className="p-3 bg-slate-900/40 border border-border-dark/65 rounded-none hover:border-slate-700 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-2 mb-1.5">
                      <span className="text-xs font-semibold text-slate-200 truncate">
                        {e.properties.name || e.properties.title || e.properties.value || e.id}
                      </span>
                      <span
                        className={`text-[9px] px-1.5 py-0.5 rounded-none font-bold uppercase border ${colors.bg} ${colors.text} ${colors.border}`}
                      >
                        {e.label}
                      </span>
                    </div>
                    {Object.entries(e.properties).map(([k, v]) => {
                      if (['name', 'title', 'value'].includes(k)) return null;
                      return (
                        <div key={k} className="text-[10px] text-slate-500 truncate">
                          <span className="font-semibold text-slate-400 capitalize">{k}:</span>{' '}
                          {String(v)}
                        </div>
                      );
                    })}
                  </div>
                );
              })
            )}
          </div>
        )}

        {!loading && activeTab === 'relations' && (
          <div className="space-y-2">
            {edges.length === 0 ? (
              <div className="text-center text-xs text-slate-600 py-12">
                No relations mapped yet.
              </div>
            ) : (
              edges.map((edge, idx) => (
                <div
                  key={idx}
                  className="p-3 bg-slate-900/40 border border-border-dark/65 rounded-none hover:border-slate-700 transition-colors text-xs space-y-1.5"
                >
                  <div className="flex justify-between items-center gap-1.5">
                    <span className="text-[10px] text-slate-400 font-semibold truncate bg-slate-800 px-2 py-0.5 rounded-none">
                      {edge.source}
                    </span>
                    <span className="text-[9px] font-mono text-accent-blue font-bold tracking-wide uppercase px-1">
                      ➔ {edge.type} ➔
                    </span>
                    <span className="text-[10px] text-slate-400 font-semibold truncate bg-slate-800 px-2 py-0.5 rounded-none">
                      {edge.target}
                    </span>
                  </div>
                  {Object.entries(edge.properties).length > 0 && (
                    <div className="pt-1.5 border-t border-border-dark/40 text-[9px] text-slate-500">
                      {Object.entries(edge.properties).map(([k, v]) => (
                        <div key={k}>
                          <span className="font-semibold text-slate-400">{k}:</span> {String(v)}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
};
