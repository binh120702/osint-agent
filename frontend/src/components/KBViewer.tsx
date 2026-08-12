import React, { useEffect, useState, useRef } from 'react';
import { Database, Network, RefreshCw, Layers } from 'lucide-react';
import type { KBEntity, KBEdge } from '../types';

interface KBViewerProps {
  threadId: string | null;
  subjectId?: string | null;
  refreshTrigger: number;
}

const LABEL_COLORS: Record<string, { bg: string; text: string; border: string; fill: string; stroke: string }> = {
  PERSON: { bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/20', fill: '#f87171', stroke: '#ef4444' },
  ORGANIZATION: { bg: 'bg-blue-500/10', text: 'text-blue-400', border: 'border-blue-500/20', fill: '#60a5fa', stroke: '#3b82f6' },
  LOCATION: { bg: 'bg-green-500/10', text: 'text-green-400', border: 'border-green-500/20', fill: '#34d399', stroke: '#10b981' },
  EMAIL: { bg: 'bg-yellow-500/10', text: 'text-yellow-400', border: 'border-yellow-500/20', fill: '#fbbf24', stroke: '#f59e0b' },
  PHONE: { bg: 'bg-purple-500/10', text: 'text-purple-400', border: 'border-purple-500/20', fill: '#c084fc', stroke: '#a855f7' },
  DOMAIN: { bg: 'bg-cyan-500/10', text: 'text-cyan-400', border: 'border-cyan-500/20', fill: '#22d3ee', stroke: '#06b6d4' },
  IP_ADDRESS: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/20', fill: '#34d399', stroke: '#059669' },
  IMAGE: { bg: 'bg-pink-500/10', text: 'text-pink-400', border: 'border-pink-500/20', fill: '#f472b6', stroke: '#ec4899' },
  DEFAULT: { bg: 'bg-slate-500/10', text: 'text-slate-400', border: 'border-slate-500/20', fill: '#94a3b8', stroke: '#64748b' },
};

const formatPropertyValue = (value: any): string => {
  if (value && typeof value === 'object') {
    if (Array.isArray(value)) {
      return value.map((item) => item && typeof item === 'object' && 'value' in item ? item.value : String(item)).join(', ');
    }
    return JSON.stringify(value);
  }
  return String(value ?? '');
};

const MetadataRows: React.FC<{ metadata: any }> = ({ metadata }) => {
  if (!metadata || typeof metadata !== 'object' || Object.keys(metadata).length === 0) return null;
  return <div className="mt-2 border-t border-border-dark/50 pt-2">
    <div className="mb-1 text-[9px] font-bold uppercase tracking-wider text-accent-blue">Confirmed metadata</div>
    {Object.entries(metadata).map(([key, rawValues]) => {
      const values = Array.isArray(rawValues) ? rawValues : [rawValues];
      const rendered = values.map((item: any) => item && typeof item === 'object' && 'value' in item ? item.value : item);
      return <div key={key} className="text-[10px] break-words"><span className="font-semibold text-slate-500">{key.replaceAll('_', ' ')}:</span>{' '}{rendered.join(', ')}{values.length > 1 && <span className="ml-1 text-amber-400">conflict</span>}</div>;
    })}
  </div>;
};

interface SimNode {
  id: string;
  label: string;
  name: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  properties: any;
}

export const KBViewer: React.FC<KBViewerProps> = ({ threadId, subjectId, refreshTrigger }) => {
  const [activeTab, setActiveTab] = useState<'graph' | 'entities' | 'relations'>('graph');
  const [entities, setEntities] = useState<KBEntity[]>([]);
  const [edges, setEdges] = useState<KBEdge[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedNode, setSelectedNode] = useState<SimNode | null>(null);

  // SVG Pan/Zoom state
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const isPanningRef = useRef(false);
  const panStartRef = useRef({ x: 0, y: 0 });

  // Force simulation nodes
  const [visualNodes, setVisualNodes] = useState<SimNode[]>([]);
  const simNodesRef = useRef<SimNode[]>([]);
  const draggedNodeIdRef = useRef<string | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const fetchKB = async () => {
    const namespace = subjectId || threadId;
    if (!namespace) {
      setEntities([]);
      setEdges([]);
      setVisualNodes([]);
      simNodesRef.current = [];
      return;
    }
    setLoading(true);
    try {
      const [entRes, edgeRes] = await Promise.all([
        fetch(subjectId ? `/api/subjects/${subjectId}/entities` : `/api/kb/${threadId}/entities`),
        fetch(subjectId ? `/api/subjects/${subjectId}/edges` : `/api/kb/${threadId}/edges`),
      ]);
      if (entRes.ok) {
        const entData = await entRes.json();
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
  }, [threadId, subjectId, refreshTrigger]);

  // Force-directed layout simulation loop
  useEffect(() => {
    if (entities.length === 0) {
      setVisualNodes([]);
      simNodesRef.current = [];
      return;
    }

    const width = 300;
    const height = 350;

    // Build or update simulation nodes
    const simulationNodes: SimNode[] = entities.map(entity => {
      const existing = simNodesRef.current.find(sn => sn.id === entity.id);
      return {
        id: entity.id,
        label: entity.label,
        name: entity.properties.name || entity.properties.title || entity.id,
        x: existing ? existing.x : width / 2 + (Math.random() - 0.5) * 120,
        y: existing ? existing.y : height / 2 + (Math.random() - 0.5) * 120,
        vx: existing ? existing.vx : 0,
        vy: existing ? existing.vy : 0,
        properties: entity.properties,
      };
    });

    simNodesRef.current = simulationNodes;

    let animationFrameId: number;

    const runSimulation = () => {
      // 1. Repulsion between all node pairs (Electrostatic-like force)
      for (let i = 0; i < simulationNodes.length; i++) {
        const nodeA = simulationNodes[i];
        for (let j = i + 1; j < simulationNodes.length; j++) {
          const nodeB = simulationNodes[j];
          const dx = nodeB.x - nodeA.x;
          const dy = nodeB.y - nodeA.y;
          const distSq = dx * dx + dy * dy || 1;
          const dist = Math.sqrt(distSq);

          const force = Math.min(450 / distSq, 8); // cap max repulsion force
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;

          if (nodeA.id !== draggedNodeIdRef.current) {
            nodeA.vx -= fx;
            nodeA.vy -= fy;
          }
          if (nodeB.id !== draggedNodeIdRef.current) {
            nodeB.vx += fx;
            nodeB.vy += fy;
          }
        }
      }

      // 2. Attraction along edges (Spring force)
      edges.forEach(link => {
        const sourceNode = simulationNodes.find(n => n.name.toLowerCase() === link.source.toLowerCase());
        const targetNode = simulationNodes.find(n => n.name.toLowerCase() === link.target.toLowerCase());

        if (sourceNode && targetNode) {
          const dx = targetNode.x - sourceNode.x;
          const dy = targetNode.y - sourceNode.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;

          // Target link distance = 90px
          const force = (dist - 90) * 0.035;
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;

          if (sourceNode.id !== draggedNodeIdRef.current) {
            sourceNode.vx += fx;
            sourceNode.vy += fy;
          }
          if (targetNode.id !== draggedNodeIdRef.current) {
            targetNode.vx -= fx;
            targetNode.vy -= fy;
          }
        }
      });

      // 3. Center pull & update positions
      simulationNodes.forEach(node => {
        if (node.id === draggedNodeIdRef.current) {
          node.vx = 0;
          node.vy = 0;
        } else {
          // Pull to SVG center
          const cx = width / 2;
          const cy = height / 2;
          node.vx += (cx - node.x) * 0.008;
          node.vy += (cy - node.y) * 0.008;

          node.x += node.vx;
          node.y += node.vy;
          node.vx *= 0.82; // damping factor
          node.vy *= 0.82;
        }
      });

      setVisualNodes([...simulationNodes]);
      animationFrameId = requestAnimationFrame(runSimulation);
    };

    animationFrameId = requestAnimationFrame(runSimulation);
    return () => cancelAnimationFrame(animationFrameId);
  }, [entities, edges]);

  // Dragging event handlers for nodes
  const handleNodeMouseDown = (e: React.MouseEvent, node: SimNode) => {
    e.stopPropagation();
    draggedNodeIdRef.current = node.id;
    setSelectedNode(node);
  };

  const handleContainerMouseMove = (e: React.MouseEvent) => {
    if (draggedNodeIdRef.current && svgRef.current) {
      const rect = svgRef.current.getBoundingClientRect();
      const clientX = e.clientX - rect.left;
      const clientY = e.clientY - rect.top;
      
      const x = (clientX - pan.x) / zoom;
      const y = (clientY - pan.y) / zoom;

      const node = simNodesRef.current.find(n => n.id === draggedNodeIdRef.current);
      if (node) {
        node.x = x;
        node.y = y;
        node.vx = 0;
        node.vy = 0;
      }
    } else if (isPanningRef.current) {
      const dx = e.clientX - panStartRef.current.x;
      const dy = e.clientY - panStartRef.current.y;
      setPan({ x: pan.x + dx, y: pan.y + dy });
      panStartRef.current = { x: e.clientX, y: e.clientY };
    }
  };

  const handleContainerMouseUp = () => {
    draggedNodeIdRef.current = null;
    isPanningRef.current = false;
  };

  const handleSvgMouseDown = (e: React.MouseEvent) => {
    if (e.button === 0) { // left click canvas to pan
      isPanningRef.current = true;
      panStartRef.current = { x: e.clientX, y: e.clientY };
    }
  };

  const handleWheel = (e: React.WheelEvent) => {
    const zoomFactor = e.deltaY < 0 ? 1.08 : 0.92;
    const nextZoom = Math.max(0.4, Math.min(2.5, zoom * zoomFactor));
    setZoom(nextZoom);
  };

  const resetViewport = () => {
    setPan({ x: 0, y: 0 });
    setZoom(1);
    setSelectedNode(null);
  };

  if (!threadId && !subjectId) {
    return (
      <div className="w-80 bg-panel-dark border-l border-border-dark flex flex-col items-center justify-center p-6 text-center text-slate-500 text-xs">
        <Network className="w-10 h-10 mb-3 text-slate-700 stroke-[1.5]" />
        Select a thread to view extracted Knowledge Graph entities and relationships.
      </div>
    );
  }

  return (
    <div className="w-80 bg-panel-dark border-l border-border-dark flex flex-col h-full overflow-hidden select-none">
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

      {/* Tabs */}
      <div className="flex border-b border-border-dark bg-slate-950/40 p-1 m-2 rounded-none">
        <button
          onClick={() => setActiveTab('graph')}
          className={`flex-1 py-1.5 text-xs font-semibold rounded-none transition-colors flex items-center justify-center gap-1.5 ${
            activeTab === 'graph'
              ? 'bg-accent-blue/15 text-accent-blue'
              : 'text-slate-400 hover:text-slate-300'
          }`}
        >
          <Network className="w-3.5 h-3.5" />
          Graph View
        </button>
        <button
          onClick={() => setActiveTab('entities')}
          className={`flex-1 py-1.5 text-xs font-semibold rounded-none transition-colors flex items-center justify-center gap-1.5 ${
            activeTab === 'entities'
              ? 'bg-accent-blue/15 text-accent-blue'
              : 'text-slate-400 hover:text-slate-300'
          }`}
        >
          <Layers className="w-3.5 h-3.5" />
          Nodes ({entities.length})
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

      <div className="flex-1 overflow-hidden flex flex-col relative">
        {loading && (
          <div className="absolute inset-0 bg-panel-dark/80 flex items-center justify-center z-10 text-slate-500 text-xs">
            <RefreshCw className="animate-spin w-4 h-4 mr-2" />
            Updating view...
          </div>
        )}

        {/* Tab content 1: Interactive SVG Force Graph */}
        {activeTab === 'graph' && (
          <div className="flex-1 flex flex-col overflow-hidden relative">
            <div className="absolute top-2 right-2 flex gap-1 z-10">
              <button 
                onClick={resetViewport}
                className="px-2 py-1 bg-slate-900 border border-border-dark text-[10px] text-slate-400 hover:text-slate-200 hover:border-slate-700"
                title="Reset Pan/Zoom"
              >
                Reset View
              </button>
            </div>

            {entities.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center text-slate-600 text-xs p-6 text-center">
                <Network className="w-8 h-8 mb-2 text-slate-800 stroke-[1.5]" />
                Graph is empty. Use knowledge_agent tool to extract facts.
              </div>
            ) : (
              <div className="flex-1 w-full h-full relative overflow-hidden bg-slate-950/45">
                <svg
                  ref={svgRef}
                  className="w-full h-full cursor-grab active:cursor-grabbing"
                  onMouseMove={handleContainerMouseMove}
                  onMouseUp={handleContainerMouseUp}
                  onMouseLeave={handleContainerMouseUp}
                  onMouseDown={handleSvgMouseDown}
                  onWheel={handleWheel}
                >
                  <defs>
                    <marker
                      id="arrow"
                      viewBox="0 0 10 10"
                      refX="17"
                      refY="5"
                      markerWidth="6"
                      markerHeight="6"
                      orient="auto-start-reverse"
                    >
                      <path d="M 0 1 L 10 5 L 0 9 z" fill="#38bdf8" opacity="0.65" />
                    </marker>
                  </defs>

                  <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
                    {/* Edges */}
                    {edges.map((edge, idx) => {
                      const sourceNode = visualNodes.find(n => n.name.toLowerCase() === edge.source.toLowerCase());
                      const targetNode = visualNodes.find(n => n.name.toLowerCase() === edge.target.toLowerCase());
                      if (!sourceNode || !targetNode) return null;

                      return (
                        <g key={idx}>
                          <line
                            x1={sourceNode.x}
                            y1={sourceNode.y}
                            x2={targetNode.x}
                            y2={targetNode.y}
                            stroke="#38bdf8"
                            strokeWidth="1.2"
                            strokeDasharray="4,3"
                            opacity="0.35"
                            markerEnd="url(#arrow)"
                          />
                          {/* Small relationship label in center of link */}
                          <text
                            x={(sourceNode.x + targetNode.x) / 2}
                            y={(sourceNode.y + targetNode.y) / 2 - 3}
                            fill="#0ea5e9"
                            fontSize="7px"
                            fontWeight="bold"
                            textAnchor="middle"
                            opacity="0.75"
                            className="pointer-events-none font-mono"
                          >
                            {edge.type.toLowerCase()}
                          </text>
                        </g>
                      );
                    })}

                    {/* Nodes */}
                    {visualNodes.map(node => {
                      const colors = LABEL_COLORS[node.label.toUpperCase()] || LABEL_COLORS.DEFAULT;
                      const isSelected = selectedNode?.id === node.id;

                      return (
                        <g
                          key={node.id}
                          transform={`translate(${node.x}, ${node.y})`}
                          onMouseDown={(e) => handleNodeMouseDown(e, node)}
                          className="cursor-pointer group"
                        >
                          {/* Outer highlight circle */}
                          <circle
                            r="11"
                            fill="none"
                            stroke={isSelected ? '#38bdf8' : 'none'}
                            strokeWidth="1.5"
                            opacity="0.85"
                          />
                          {/* Inner main circle */}
                          <circle
                            r="7.5"
                            fill={colors.fill}
                            stroke={colors.stroke}
                            strokeWidth="1.5"
                            className="group-hover:scale-110 transition-transform"
                          />
                          {/* Text node label */}
                          <text
                            y="-11"
                            fill="#e2e8f0"
                            fontSize="8px"
                            fontWeight="semibold"
                            textAnchor="middle"
                            className="pointer-events-none select-none font-sans drop-shadow-[0_1px_1px_rgba(0,0,0,0.85)]"
                          >
                            {node.name.length > 15 ? node.name.slice(0, 13) + '..' : node.name}
                          </text>
                        </g>
                      );
                    })}
                  </g>
                </svg>
              </div>
            )}

            {/* Selected Node Details Card at bottom of Graph */}
            {selectedNode && (
              <div className="p-3 bg-slate-900 border-t border-border-dark/80 text-xs text-slate-400 space-y-1.5 flex-shrink-0 animate-slide-up">
                <div className="flex items-start justify-between">
                  <span className="font-bold text-slate-200 text-[11px] truncate pr-2">
                    {selectedNode.name}
                  </span>
                  <span className="text-[8px] font-extrabold uppercase px-1 py-0.5 bg-slate-800 border border-slate-700 text-slate-400 rounded-none flex-shrink-0">
                    {selectedNode.label}
                  </span>
                </div>
                {Object.entries(selectedNode.properties).map(([k, v]) => {
                  if (['name', 'title', 'value', 'metadata'].includes(k)) return null;
                  return (
                    <div key={k} className="text-[10px] break-words">
                      <span className="font-semibold text-slate-500 capitalize">{k}:</span>{' '}
                      {formatPropertyValue(v)}
                    </div>
                  );
                })}
                <MetadataRows metadata={selectedNode.properties.metadata} />
              </div>
            )}
          </div>
        )}

        {/* Tab content 2: Nodes List */}
        {activeTab === 'entities' && (
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
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
                      if (['name', 'title', 'value', 'metadata'].includes(k)) return null;
                      return (
                        <div key={k} className="text-[10px] text-slate-500 truncate">
                          <span className="font-semibold text-slate-400 capitalize">{k}:</span>{' '}
                          {formatPropertyValue(v)}
                        </div>
                      );
                    })}
                    <MetadataRows metadata={e.properties.metadata} />
                  </div>
                );
              })
            )}
          </div>
        )}

        {/* Tab content 3: Edges List */}
        {activeTab === 'relations' && (
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
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
