import React, { useCallback, useEffect, useRef, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import type { GraphData, OntologyNode, Persona } from '../../types/knowledge';
import { fetchGraph } from '../../services/knowledgeApi';

const NODE_COLORS: Record<string, string> = {
  CLO: '#6366f1',
  ABS: '#8b5cf6',
  RMBS: '#a78bfa',
  CMBS: '#c4b5fd',
  Instrument: '#6366f1',
  SME: '#7c3aed',
  Originator: '#06b6d4',
  Issuer: '#06b6d4',
  SPV: '#0891b2',
  Finding: '#f59e0b',
  FindingCluster_ok:   '#22c55e',   // all compliant
  FindingCluster_warn: '#f59e0b',   // needs review
  FindingCluster_bad:  '#ef4444',   // non-compliant
  Tranche: '#10b981',
  Document: '#22d3ee',
  Rule: '#ec4899',
  default: '#94a3b8',
};

/** Collapse finding nodes into per-ruleId cluster nodes */
function buildCompactGraph(graphData: GraphData): GraphData {
  const findingNodes = graphData.nodes.filter(n => n.type === 'Finding');
  const otherNodes   = graphData.nodes.filter(n => n.type !== 'Finding');

  // Group by rule name (text before ' - ')
  const groups: Record<string, OntologyNode[]> = {};
  for (const n of findingNodes) {
    const key = (n.label ?? n.id).split('-')[0].trim();
    (groups[key] ??= []).push(n);
  }

  // Build a mapping from original finding id -> cluster id
  const toCluster: Record<string, string> = {};
  for (const n of findingNodes) {
    const key = (n.label ?? n.id).split('-')[0].trim();
    toCluster[n.id] = `cluster:${key}`;
  }

  const clusterNodes: OntologyNode[] = Object.entries(groups).map(([key, nodes]) => {
    const hasBad  = nodes.some(n => (n.label ?? '').toLowerCase().includes('non_compliant'));
    const hasWarn = nodes.some(n => !hasBad && (n.label ?? '').toLowerCase().includes('needs_review'));
    const verdict = hasBad ? '[fail]' : hasWarn ? '[warn]' : '[ok]';
    const clusterType = hasBad ? 'FindingCluster_bad' : hasWarn ? 'FindingCluster_warn' : 'FindingCluster_ok';
    return {
      id: `cluster:${key}`,
      type: clusterType,
      label: `${key} (${nodes.length}) ${verdict}`,
      val: Math.max(4, nodes.length * 1.8),
    } as OntologyNode;
  });

  // Deduplicate edges after remapping finding -> cluster
  const seen = new Set<string>();
  const clusterEdges = graphData.edges
    .map(e => ({
      id: `${(toCluster[e.source] ?? e.source)}→${(toCluster[e.target] ?? e.target)}`,
      source: toCluster[e.source] ?? e.source,
      target: toCluster[e.target] ?? e.target,
      relation: e.relation,
    }))
    .filter(e => {
      if (e.source === e.target) return false;
      if (seen.has(e.id)) return false;
      seen.add(e.id);
      return true;
    });

  return { nodes: [...otherNodes, ...clusterNodes], edges: clusterEdges };
}

interface GraphVisualizationProps {
  persona: Persona | null;
  hint?: string;
  highlightDocName?: string | null;
  onNodeClick?: (node: OntologyNode) => void;
}

export function GraphVisualization({ persona, hint, highlightDocName, onNodeClick }: GraphVisualizationProps) {
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], edges: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [groupMode, setGroupMode] = useState<'compact' | 'full'>('compact');
  const containerRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<any>(null);
  const [dimensions, setDimensions] = useState({ width: 600, height: 400 });

  // Configure force simulation - called whenever graphData or groupMode changes
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;
    fg.d3Force('charge')?.strength(-350);
    fg.d3Force('link')?.distance((l: any) => {
      const srcType = typeof l.source === 'object' ? l.source.type : '';
      const tgtType = typeof l.target === 'object' ? l.target.type : '';
      if (srcType === 'Document' || tgtType === 'Document') return 120;
      if (srcType?.startsWith('FindingCluster') || tgtType?.startsWith('FindingCluster')) return 100;
      return 80;
    });
    // Add collision so nodes never overlap
    try {
      const d3 = (fg as any).d3Force('charge').__proto__.constructor;
      void d3; // just to check import exists
    } catch { /* ok */ }
    fg.d3ReheatSimulation();
  }, [graphData, groupMode]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchGraph(persona, hint);
      setGraphData(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load graph');
    } finally {
      setLoading(false);
    }
  }, [persona, hint]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      setDimensions({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Active display data (compact or full)
  const activeData = React.useMemo(
    () => groupMode === 'compact' ? buildCompactGraph(graphData) : graphData,
    [graphData, groupMode],
  );

  // Build highlighted ID set from active data
  const highlightedIds = React.useMemo(() => {
    if (!highlightDocName) return null;
    const nameLower = highlightDocName.toLowerCase();
    const stemLower = nameLower.replace(/\.txt$/i, '').replace(/_/g, ' ');

    const docNode = activeData.nodes.find(
      n => n.type === 'Document' && (
        n.label?.toLowerCase() === nameLower ||
        n.label?.toLowerCase() === stemLower
      )
    );
    if (!docNode) return null;

    const docUUID = docNode.id.replace('urn:document:', '');
    const instId  = `urn:instrument:${docUUID}`;
    const ids = new Set<string>([docNode.id, instId]);

    const edgeList = activeData.edges as any[];
    for (let pass = 0; pass < 2; pass++) {
      edgeList.forEach(e => {
        const src = typeof e.source === 'object' ? e.source.id : e.source;
        const tgt = typeof e.target === 'object' ? e.target.id : e.target;
        if (ids.has(src)) ids.add(tgt);
        if (ids.has(tgt)) ids.add(src);
      });
    }

    const docInGraph  = activeData.nodes.some(n => n.id === docNode.id);
    const instInGraph = activeData.nodes.some(n => n.id === instId);
    if (!docInGraph && !instInGraph) return null;
    return ids;
  }, [highlightDocName, activeData]);

  const highlightMissing = !!highlightDocName && !highlightedIds;

  useEffect(() => {
    if (!fgRef.current || !highlightedIds) return;
    setTimeout(() => {
      fgRef.current.zoomToFit(400, 80, (n: any) => highlightedIds.has(n.id));
    }, 700);
  }, [highlightedIds]);

  const fgData = {
    nodes: activeData.nodes.map(n => ({ ...n })),
    links: activeData.edges.map(e => ({ source: e.source, target: e.target, label: e.relation })),
  };

  return (
    <div ref={containerRef} className="relative h-full w-full overflow-hidden rounded-xl bg-gray-950">
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-gray-400 text-sm animate-pulse">Loading graph...</div>
        </div>
      )}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}
      {!loading && !error && fgData.nodes.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center text-gray-600 text-sm">
          No nodes - process a document first or seed the synthetic graph.
        </div>
      )}
      {!loading && !error && fgData.nodes.length > 0 && (
        <ForceGraph2D
          ref={fgRef}
          width={dimensions.width}
          height={dimensions.height}
          graphData={fgData}
          nodeLabel={(n: any) => `${n.type}: ${n.label || n.id}`}
          nodeVal={(n: any) => n.val ?? 4}
          nodeColor={(n: any) => {
            const baseColor = NODE_COLORS[n.type] ?? NODE_COLORS.default;
            if (highlightedIds) {
              return highlightedIds.has(n.id) ? baseColor : '#1e293b';
            }
            return baseColor;
          }}
          nodeRelSize={4}
          linkLabel={(l: any) => l.label ?? ''}
          linkColor={(l: any) => {
            if (!highlightedIds) return '#334155';
            const src = typeof l.source === 'object' ? l.source.id : l.source;
            const tgt = typeof l.target === 'object' ? l.target.id : l.target;
            return (highlightedIds.has(src) && highlightedIds.has(tgt)) ? '#6366f1' : '#1e293b';
          }}
          linkWidth={(l: any) => {
            if (!highlightedIds) return 1;
            const src = typeof l.source === 'object' ? l.source.id : l.source;
            const tgt = typeof l.target === 'object' ? l.target.id : l.target;
            return (highlightedIds.has(src) && highlightedIds.has(tgt)) ? 2 : 0.3;
          }}
          linkDirectionalArrowLength={3}
          linkDirectionalArrowRelPos={1}
          d3AlphaDecay={0.025}
          d3VelocityDecay={0.35}
          onNodeClick={(n: any) => onNodeClick?.(n as OntologyNode)}
          backgroundColor="#030712"
          nodeCanvasObjectMode={() => 'after'}
          nodeCanvasObject={(node: any, ctx, globalScale) => {
            const dimmed = highlightedIds && !highlightedIds.has(node.id);
            if (dimmed) return;
            if (globalScale < 0.45) return;   // hide labels when zoomed out
            const label: string = node.label ?? node.id ?? '';
            const isCluster = node.type?.startsWith('FindingCluster');
            const fontSize = Math.max(7, (isCluster ? 10 : 9) / globalScale);
            ctx.font = `${isCluster ? '600 ' : ''}${fontSize}px Sans-Serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'top';
            // background pill for clusters so text is readable
            if (isCluster && globalScale >= 0.55) {
              const textW = ctx.measureText(label.slice(0, 40)).width;
              const pad = 3 / globalScale;
              const rx = node.x - textW / 2 - pad;
              const ry = node.y + (node.val ?? 4) * 1.4;
              ctx.fillStyle = 'rgba(3,7,18,0.75)';
              ctx.fillRect(rx, ry, textW + pad * 2, fontSize + 2 / globalScale);
            }
            ctx.fillStyle = isCluster ? '#f1f5f9' : '#94a3b8';
            ctx.fillText(label.slice(0, 40), node.x, node.y + (node.val ?? 4) * 1.5 + fontSize * 0.2);
          }}
        />
      )}

      {/* Toolbar */}
      <div className="absolute top-3 right-3 flex items-center gap-1.5">
        {/* Compact / Full toggle */}
        <div className="flex rounded-lg overflow-hidden border border-gray-700 text-[10px]">
          <button
            onClick={() => setGroupMode('compact')}
            className={`px-2.5 py-1 transition-colors ${groupMode === 'compact' ? 'bg-indigo-600 text-white' : 'bg-gray-800/80 text-gray-400 hover:text-white'}`}
          >
            Compact
          </button>
          <button
            onClick={() => setGroupMode('full')}
            className={`px-2.5 py-1 transition-colors ${groupMode === 'full' ? 'bg-indigo-600 text-white' : 'bg-gray-800/80 text-gray-400 hover:text-white'}`}
          >
            Full
          </button>
        </div>
        {/* Zoom to fit */}
        <button
          onClick={() => fgRef.current?.zoomToFit(400, 40)}
          className="rounded-lg bg-gray-800/80 px-2 py-1 text-xs text-gray-300 hover:bg-gray-700 transition-colors"
          title="Zoom to fit"
        >
          Fit
        </button>
        {/* Refresh */}
        <button
          onClick={load}
          className="rounded-lg bg-gray-800/80 px-2 py-1 text-xs text-gray-300 hover:bg-gray-700 transition-colors"
        >
          Reload
        </button>
      </div>

      {/* Node count badge */}
      <div className="absolute top-3 left-3 rounded-lg bg-gray-800/70 px-2 py-1 text-[10px] text-gray-400">
        {fgData.nodes.length} nodes - {fgData.links.length} edges
        {groupMode === 'compact' && graphData.nodes.filter(n => n.type === 'Finding').length > 0 && (
          <span className="ml-1.5 text-indigo-400">
            ({graphData.nodes.filter(n => n.type === 'Finding').length} findings grouped)
          </span>
        )}
      </div>

      {/* "Document not enriched" hint banner */}
      {highlightMissing && (
        <div className="absolute top-10 left-1/2 -translate-x-1/2 rounded-lg bg-amber-900/80 border border-amber-600/50 px-3 py-2 text-xs text-amber-200 shadow-lg text-center max-w-xs">
          <span className="font-semibold">{highlightDocName?.replace(/\.txt$/i, '').replace(/_/g, ' ')}</span>
          {' '}is not yet in the graph.
          Go to <span className="font-semibold">Ingest &gt; Re-enrich</span> to add it.
        </div>
      )}

      {/* Legend */}
      <div className="absolute bottom-3 left-3 flex flex-wrap gap-2">
        {[
          ['Document', NODE_COLORS.Document],
          ['Instrument', NODE_COLORS.Instrument],
          ['Compliant', NODE_COLORS.FindingCluster_ok],
          ['Needs Review', NODE_COLORS.FindingCluster_warn],
          ['Non-Compliant', NODE_COLORS.FindingCluster_bad],
          ['Rule', NODE_COLORS.Rule],
        ].map(([type, color]) => (
          <span key={type} className="flex items-center gap-1 text-[10px] text-gray-400">
            <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
            {type}
          </span>
        ))}
      </div>
    </div>
  );
}
