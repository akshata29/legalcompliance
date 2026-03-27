import React, { useState, useCallback } from 'react';
import { Brain, MessageSquare, Network, BookOpen, Settings2, BarChart2, CloudUpload } from 'lucide-react';

import type { EntityDetail, Finding, OntologyNode, Persona } from '../types/knowledge';
import { getEntity, searchEntities } from '../services/knowledgeApi';

import { PersonaSelector } from '../components/knowledge/PersonaSelector';
import { ChatInterface } from '../components/knowledge/ChatInterface';
import { GraphVisualization } from '../components/knowledge/GraphVisualization';
import { EntityCard } from '../components/knowledge/EntityCard';
import { RuleExplorer } from '../components/knowledge/RuleExplorer';
import { BatchMonitor } from '../components/knowledge/BatchMonitor';
import { SMEApprovalQueue } from '../components/knowledge/SMEApprovalQueue';
import { TelemetryPanel } from '../components/knowledge/TelemetryPanel';
import { DocumentIngest } from '../components/knowledge/DocumentIngest';

type RightTab = 'entity' | 'rules' | 'ingest' | 'admin' | 'telemetry';

const RIGHT_TABS: { id: RightTab; label: string; icon: React.ReactNode }[] = [
  { id: 'entity',    label: 'Entity',    icon: <BookOpen size={14} /> },
  { id: 'rules',     label: 'Rules',     icon: <Brain size={14} /> },
  { id: 'ingest',    label: 'Ingest',    icon: <CloudUpload size={14} /> },
  { id: 'admin',     label: 'Admin',     icon: <Settings2 size={14} /> },
  { id: 'telemetry', label: 'Telemetry', icon: <BarChart2 size={14} /> },
];

export default function KnowledgeGraph() {
  const [persona, setPersona] = useState<Persona | null>('legal');
  const [selectedNode, setSelectedNode] = useState<OntologyNode | null>(null);
  const [entityDetail, setEntityDetail] = useState<EntityDetail[]>([]);
  const [entityFindings, setEntityFindings] = useState<Finding[]>([]);
  const [entityLoading, setEntityLoading] = useState(false);
  const [rightTab, setRightTab] = useState<RightTab>('entity');
  const [mainView, setMainView] = useState<'chat' | 'graph'>('chat');
  const [graphKey, setGraphKey] = useState(0); // increment to force graph refresh
  const [docHighlight, setDocHighlight] = useState<string | null>(null);

  const handleGraphUpdated = useCallback(() => {
    setGraphKey(k => k + 1);
  }, []);

  const handleViewInGraph = useCallback((docName: string) => {
    setDocHighlight(docName);
    setMainView('graph');
  }, []);

  const handleNodeClick = async (node: OntologyNode) => {
    setSelectedNode(node);
    setDocHighlight(null); // clear doc highlight when user picks a node
    setRightTab('entity');
    setEntityLoading(true);
    try {
      const data = await getEntity(node.id);
      setEntityDetail(data.detail);
      setEntityFindings(data.findings);
    } catch {
      setEntityDetail([]);
      setEntityFindings([]);
    } finally {
      setEntityLoading(false);
    }
  };

  const handleClearScope = useCallback(() => {
    setSelectedNode(null);
    setDocHighlight(null);
    setEntityDetail([]);
    setEntityFindings([]);
  }, []);

  // Called when user picks a document from the chat-window picker
  const handleSelectDocument = useCallback(async (docName: string) => {
    // Use the doc name as a search hint to find the graph node
    const stem = docName.replace(/\.txt$/i, '');
    setEntityLoading(true);
    setRightTab('entity');
    try {
      const { entities } = await searchEntities(stem);
      // Runtime shape from backend is { entity, type, label, ... } SPARQL rows
      const first = entities[0] as unknown as Record<string, string> | undefined;
      if (first?.entity) {
        // type URIs use ':' not '#' (e.g. urn:legalcompliance:core:Document)
        const typeLabel = (first.type ?? '').split(/[#:]/).filter(Boolean).pop() ?? 'Document';
        const node: OntologyNode = {
          id: first.entity,
          type: typeLabel,
          label: first.label ?? docName,
        };
        setSelectedNode(node);
        const data = await getEntity(node.id);
        setEntityDetail(data.detail);
        setEntityFindings(data.findings);
      } else {
        // Fallback: set a synthetic scope from the doc label alone
        setSelectedNode({ id: `urn:document:${stem}`, type: 'Document', label: docName } as OntologyNode);
      }
    } catch {
      setSelectedNode({ id: `urn:document:${stem}`, type: 'Document', label: docName } as OntologyNode);
    } finally {
      setEntityLoading(false);
    }
  }, []);

  // Derive instrument scope for chat.
  // Priority: clicked Instrument node > clicked Document node (same UUID) > doc highlight
  const chatInstrumentUrn =
    selectedNode?.type === 'Instrument' || selectedNode?.type === 'instrument'
      ? selectedNode.id
      : selectedNode?.type === 'Document' || selectedNode?.type === 'document'
        ? selectedNode.id   // document URI — agent normalises to instrument URI
        : null;
  const chatInstrumentLabel =
    chatInstrumentUrn
      ? (selectedNode?.label ?? selectedNode?.id ?? null)
      : docHighlight
        ? docHighlight.replace(/\.txt$/i, '').replace(/_/g, ' ')
        : null;

  return (
    <div className="flex h-screen flex-col bg-gray-50 dark:bg-gray-950 overflow-hidden">
      {/* ── Top bar ─────────────────────────────────────────────────────────── */}
      <header className="flex items-center gap-4 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 px-5 py-2.5 shadow-sm">
        {/* Brand */}
        <div className="flex items-center gap-2 shrink-0">
          <Brain className="text-indigo-600" size={20} />
          <span className="text-sm font-bold text-gray-900 dark:text-white">Knowledge Graph</span>
          <span className="hidden sm:inline text-[10px] text-gray-400 ml-1">
            FIBO · EU Sec · ERISA · OM
          </span>
        </div>

        <div className="w-px h-5 bg-gray-200 dark:bg-gray-700 shrink-0" />

        {/* Persona pills — centre */}
        <div className="flex-1 min-w-0">
          <PersonaSelector selected={persona} onChange={setPersona} />
        </div>

        {/* Chat / Graph toggle — right */}
        <div className="flex rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden text-xs shrink-0">
          <button
            onClick={() => { setMainView('chat'); setPersona(p => p ?? 'legal'); }}
            className={[
              'flex items-center gap-1.5 px-3 py-1.5 transition-colors',
              mainView === 'chat'
                ? 'bg-indigo-600 text-white'
                : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800',
            ].join(' ')}
          >
            <MessageSquare size={12} /> Chat
          </button>
          <button
            onClick={() => { setMainView('graph'); setPersona(null); }}
            className={[
              'flex items-center gap-1.5 px-3 py-1.5 transition-colors',
              mainView === 'graph'
                ? 'bg-indigo-600 text-white'
                : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800',
            ].join(' ')}
          >
            <Network size={12} /> Graph
          </button>
        </div>
      </header>

      {/* ── Two-panel layout ─────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">

        {/* CENTRE PANEL — Chat or Graph */}
        <main className="flex-1 overflow-hidden">
          {mainView === 'chat' ? (
            <ChatInterface
              persona={persona}
              instrumentUrn={chatInstrumentUrn}
              instrumentLabel={chatInstrumentLabel}
              onClearScope={handleClearScope}
              onSelectDocument={handleSelectDocument}
            />
          ) : (
            <GraphVisualization
              key={graphKey}
              persona={persona}
              highlightDocName={docHighlight}
              onNodeClick={handleNodeClick}
            />
          )}
        </main>

        {/* RIGHT PANEL — Tabbed detail */}
        <aside className="w-[440px] flex-shrink-0 border-l border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 flex flex-col overflow-hidden">
          {/* Tab bar */}
          <div className="flex border-b border-gray-200 dark:border-gray-700">
            {RIGHT_TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setRightTab(tab.id)}
                className={[
                  'flex items-center gap-1 px-3 py-2.5 text-[11px] font-medium whitespace-nowrap border-b-2 transition-colors flex-1 justify-center',
                  rightTab === tab.id
                    ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
                    : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300',
                ].join(' ')}
              >
                {tab.icon}
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="flex-1 overflow-y-auto">
            {rightTab === 'entity' && (
              <EntityCard
                node={selectedNode}
                detail={entityDetail}
                findings={entityFindings}
                loading={entityLoading}
              />
            )}
            {rightTab === 'rules' && (
              <RuleExplorer instrumentUrn={selectedNode?.id} instrumentLabel={selectedNode?.label} />
            )}
            {rightTab === 'ingest' && (
              <div className="p-3">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 mb-3">
                  Ingest Documents into Graph
                </p>
                <DocumentIngest onGraphUpdated={handleGraphUpdated} onViewInGraph={handleViewInGraph} />
              </div>
            )}
            {rightTab === 'admin' && (
              <div className="divide-y divide-gray-100 dark:divide-gray-800">
                <div className="p-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 mb-2">Batch Jobs</p>
                  <BatchMonitor />
                </div>
                <div className="p-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 mb-2">SME Queue</p>
                  <SMEApprovalQueue />
                </div>
              </div>
            )}
            {rightTab === 'telemetry' && <TelemetryPanel />}
          </div>
        </aside>
      </div>
    </div>
  );
}
