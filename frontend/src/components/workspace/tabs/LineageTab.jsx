/* ============================================================
   LineageTab.jsx — Tab 5: Visual Decision & Dependency Lineage Graph
   Interactive visual node-and-edge canvas with side inspection drawer
   ============================================================ */
import React, { useEffect, useState, useMemo, useRef } from 'react';

// Node type styling constants
const NODE_THEMES = {
  MEETING: {
    bg: '#F4EBC6',
    border: '#E9C22E',
    color: '#0D0D0C',
    tag: 'Meeting',
    icon: '📅',
  },
  DECISION_ACTIVE: {
    bg: '#DFE9D4',
    border: '#3FB874',
    color: '#0D0D0C',
    tag: 'Active Decision',
    icon: '⚖️',
  },
  DECISION_SUPERSEDED: {
    bg: '#ECD6E2',
    border: '#C564C4',
    color: '#0D0D0C',
    tag: 'Superseded',
    icon: '↩️',
    dashed: true,
  },
  CONFLICT: {
    bg: '#ECD6E2',
    border: '#C564C4',
    color: '#0D0D0C',
    tag: 'Conflict Risk',
    icon: '⚡',
    dashed: true,
  },
  TASK: {
    bg: '#FBF6EF',
    border: '#0D0D0C',
    color: '#0D0D0C',
    tag: 'Execution Task',
    icon: '📦',
  },
  STAGING_ITEM: {
    bg: '#F9CBA9',
    border: '#F2772F',
    color: '#0D0D0C',
    tag: 'Staging Item',
    icon: '⏳',
  },
};

function getNodeTheme(node) {
  if (node.type === 'MEETING') return NODE_THEMES.MEETING;
  if (node.type === 'CONFLICT') return NODE_THEMES.CONFLICT;
  if (node.type === 'TASK') return NODE_THEMES.TASK;
  if (node.type === 'STAGING_ITEM') return NODE_THEMES.STAGING_ITEM;
  if (node.type === 'DECISION') {
    if (node.status === 'SUPERSEDED') return NODE_THEMES.DECISION_SUPERSEDED;
    return NODE_THEMES.DECISION_ACTIVE;
  }
  return NODE_THEMES.TASK;
}

export function LineageTab({ state, actions }) {
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [filterType, setFilterType] = useState('ALL'); // 'ALL' | 'MEETING' | 'DECISION' | 'TASK' | 'CONFLICT'
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 40, y: 30 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  useEffect(() => {
    if (!state.lineageGraph) {
      actions.loadLineageGraph();
    }
  }, [state.lineageGraph, actions]);

  const rawGraph = state.lineageGraph || { nodes: [], edges: [], summary: {} };

  // Calculate layout coordinates for nodes
  const layoutNodes = useMemo(() => {
    const nodes = rawGraph.nodes || [];
    // Group nodes by tier/type
    const meetings = nodes.filter((n) => n.type === 'MEETING');
    const decisions = nodes.filter((n) => n.type === 'DECISION' || n.type === 'CONFLICT');
    const tasks = nodes.filter((n) => n.type === 'TASK' || n.type === 'STAGING_ITEM');

    const result = {};
    const colSpacing = 360;
    const rowSpacing = 110;

    meetings.forEach((n, idx) => {
      result[n.id] = { ...n, x: 80, y: 100 + idx * 160 };
    });

    decisions.forEach((n, idx) => {
      result[n.id] = { ...n, x: 80 + colSpacing, y: 60 + idx * rowSpacing };
    });

    tasks.forEach((n, idx) => {
      result[n.id] = { ...n, x: 80 + colSpacing * 2, y: 60 + idx * rowSpacing };
    });

    return result;
  }, [rawGraph.nodes]);

  // Filtered nodes
  const visibleNodes = useMemo(() => {
    return Object.values(layoutNodes).filter((n) => {
      if (filterType === 'ALL') return true;
      if (filterType === 'MEETING') return n.type === 'MEETING';
      if (filterType === 'DECISION') return n.type === 'DECISION';
      if (filterType === 'TASK') return n.type === 'TASK';
      if (filterType === 'CONFLICT') return n.type === 'CONFLICT' || n.status === 'SUPERSEDED' || n.status === 'CONFLICT_DETECTED';
      return true;
    });
  }, [layoutNodes, filterType]);

  const selectedNode = selectedNodeId ? layoutNodes[selectedNodeId] : null;

  // Filtered edges
  const visibleEdges = useMemo(() => {
    const nodeIds = new Set(visibleNodes.map((n) => n.id));
    return (rawGraph.edges || []).filter(
      (e) => layoutNodes[e.source] && layoutNodes[e.target] && (filterType === 'ALL' || (nodeIds.has(e.source) && nodeIds.has(e.target)))
    );
  }, [rawGraph.edges, visibleNodes, layoutNodes, filterType]);

  // Mouse pan handlers
  function handleMouseDown(e) {
    if (e.target.closest('.ws-node-card') || e.target.closest('.ws-graph-controls')) return;
    setIsDragging(true);
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
  }

  function handleMouseMove(e) {
    if (!isDragging) return;
    setPan({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
  }

  function handleMouseUp() {
    setIsDragging(false);
  }

  return (
    <div className="ws-lineage-container">
      {/* Top Bar with Controls & Filters */}
      <div className="ws-lineage-header">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <h2 style={{ fontSize: 20, fontWeight: 600, letterSpacing: '-0.02em', margin: 0 }}>
              Decision &amp; Dependency Lineage Graph
            </h2>
            <span className="ws-badge ws-badge-ready" style={{ fontSize: 11 }}>
              {rawGraph.summary?.total_nodes || visibleNodes.length} Nodes · {rawGraph.summary?.total_edges || visibleEdges.length} Connections
            </span>
          </div>
          <p style={{ fontSize: 13, color: 'rgba(13,13,12,0.56)', margin: '4px 0 0' }}>
            Interactive DAG tracking commitments from spoken origin to active code deliverables and supersede paths.
          </p>
        </div>

        {/* Legend & Filter Pills */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div className="ws-filter-pills">
            {['ALL', 'MEETING', 'DECISION', 'TASK', 'CONFLICT'].map((type) => (
              <button
                key={type}
                className={`ws-filter-pill ${filterType === type ? 'active' : ''}`}
                onClick={() => setFilterType(type)}
                type="button"
              >
                {type === 'ALL' ? 'All Entities' : type.charAt(0) + type.slice(1).toLowerCase() + 's'}
              </button>
            ))}
          </div>

          <button
            className="ws-btn ws-btn-sm"
            onClick={() => actions.loadLineageGraph()}
            disabled={state.loading.lineage}
            type="button"
          >
            {state.loading.lineage ? 'Refreshing…' : '↻ Refresh'}
          </button>
        </div>
      </div>

      {/* Main Canvas Area */}
      <div
        className="ws-lineage-viewport"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        style={{ cursor: isDragging ? 'grabbing' : 'grab' }}
      >
        {/* Floating Zoom Controls */}
        <div className="ws-graph-controls">
          <button className="ws-ctrl-btn" onClick={() => setZoom((z) => Math.min(z + 0.15, 1.8))} title="Zoom In">+</button>
          <button className="ws-ctrl-btn" onClick={() => setZoom((z) => Math.max(z - 0.15, 0.5))} title="Zoom Out">−</button>
          <button className="ws-ctrl-btn" onClick={() => { setZoom(1); setPan({ x: 40, y: 30 }); }} title="Reset Pan/Zoom">⤾</button>
        </div>

        {/* Canvas World */}
        <div
          className="ws-lineage-world"
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
            transformOrigin: '0 0',
          }}
        >
          {/* SVG Connection Lines */}
          <svg className="ws-lineage-svg" aria-hidden="true">
            <defs>
              <marker
                id="arrow-solid"
                viewBox="0 0 10 10"
                refX="8"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 1 L 9 5 L 0 9 z" fill="#0D0D0C" />
              </marker>
              <marker
                id="arrow-rose"
                viewBox="0 0 10 10"
                refX="8"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 1 L 9 5 L 0 9 z" fill="#C564C4" />
              </marker>
              <marker
                id="arrow-amber"
                viewBox="0 0 10 10"
                refX="8"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 1 L 9 5 L 0 9 z" fill="#F2772F" />
              </marker>
            </defs>

            {visibleEdges.map((edge, idx) => {
              const src = layoutNodes[edge.source];
              const tgt = layoutNodes[edge.target];
              if (!src || !tgt) return null;

              const isConflict = edge.relation === 'CONFLICTS_WITH' || edge.relation === 'SUPERSEDES';
              const isBlocker = edge.relation === 'BLOCKS';
              const isSelected = selectedNodeId === edge.source || selectedNodeId === edge.target;

              // Path computation (bezier curve)
              const x1 = src.x + 240;
              const y1 = src.y + 40;
              const x2 = tgt.x;
              const y2 = tgt.y + 40;
              const cx1 = x1 + Math.abs(x2 - x1) * 0.5;
              const cy1 = y1;
              const cx2 = x2 - Math.abs(x2 - x1) * 0.5;
              const cy2 = y2;
              const pathData = `M ${x1} ${y1} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${x2} ${y2}`;

              let stroke = 'rgba(13, 13, 12, 0.45)';
              let marker = 'url(#arrow-solid)';
              if (isConflict) {
                stroke = '#C564C4';
                marker = 'url(#arrow-rose)';
              } else if (isBlocker) {
                stroke = '#F2772F';
                marker = 'url(#arrow-amber)';
              }

              return (
                <g key={`${edge.source}-${edge.target}-${idx}`}>
                  <path
                    d={pathData}
                    fill="none"
                    stroke={stroke}
                    strokeWidth={isSelected ? 2.4 : 1.4}
                    strokeDasharray={isConflict ? '5,5' : 'none'}
                    markerEnd={marker}
                    opacity={selectedNodeId ? (isSelected ? 1 : 0.2) : 0.75}
                  />
                  {/* Midpoint relation pill */}
                  <text
                    x={(x1 + x2) / 2}
                    y={(y1 + y2) / 2 - 4}
                    fill={stroke}
                    fontSize="9"
                    fontWeight="600"
                    textAnchor="middle"
                    opacity={selectedNodeId ? (isSelected ? 1 : 0.2) : 0.85}
                  >
                    {edge.relation}
                  </text>
                </g>
              );
            })}
          </svg>

          {/* Node Cards */}
          {visibleNodes.map((node) => {
            const theme = getNodeTheme(node);
            const isSelected = selectedNodeId === node.id;

            return (
              <div
                key={node.id}
                className={`ws-node-card ${isSelected ? 'selected' : ''}`}
                style={{
                  transform: `translate(${node.x}px, ${node.y}px)`,
                  backgroundColor: theme.bg,
                  borderColor: isSelected ? '#0D0D0C' : theme.border,
                  borderStyle: theme.dashed ? 'dashed' : 'solid',
                  boxShadow: isSelected ? '0 0 0 3px rgba(13,13,12,0.18)' : '0 2px 8px rgba(0,0,0,0.04)',
                }}
                onClick={() => setSelectedNodeId(node.id === selectedNodeId ? null : node.id)}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6, marginBottom: 4 }}>
                  <span style={{ fontSize: 13 }}>{theme.icon}</span>
                  <span
                    className="ws-badge"
                    style={{
                      fontSize: 9,
                      padding: '1px 6px',
                      height: 18,
                      background: 'rgba(13,13,12,0.08)',
                      borderColor: 'rgba(13,13,12,0.15)',
                    }}
                  >
                    {theme.tag}
                  </span>
                </div>

                <div
                  style={{
                    fontSize: 12,
                    fontWeight: 600,
                    color: theme.color,
                    lineHeight: 1.35,
                    maxHeight: 46,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    display: '-webkit-box',
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: 'vertical',
                  }}
                >
                  {node.label}
                </div>

                {node.meta?.owner && (
                  <div style={{ fontSize: 10, color: 'rgba(13,13,12,0.5)', marginTop: 4 }}>
                    👤 {node.meta.owner} {node.meta.deadline ? `· ⏰ ${node.meta.deadline}` : ''}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Side Inspection Drawer */}
      {selectedNode && (
        <div className="ws-lineage-inspector">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
            <div>
              <span className="ws-badge ws-badge-low" style={{ marginBottom: 4, textTransform: 'uppercase' }}>
                {selectedNode.type} INSPECTION
              </span>
              <h3 style={{ fontSize: 15, fontWeight: 600, margin: 0, color: '#0D0D0C' }}>
                {selectedNode.label}
              </h3>
            </div>
            <button className="ws-modal-close" onClick={() => setSelectedNodeId(null)}>✕</button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 12, color: 'rgba(13,13,12,0.7)' }}>
            <div>
              <strong>Status:</strong>{' '}
              <span className="ws-badge ws-badge-ready" style={{ marginLeft: 4 }}>
                {selectedNode.status || 'ACTIVE'}
              </span>
            </div>

            {selectedNode.meta?.decided_by && (
              <div><strong>Decided By:</strong> {selectedNode.meta.decided_by}</div>
            )}
            {selectedNode.meta?.owner && (
              <div><strong>Owner:</strong> {selectedNode.meta.owner}</div>
            )}
            {selectedNode.meta?.deadline && (
              <div><strong>Deadline:</strong> {selectedNode.meta.deadline}</div>
            )}
            {selectedNode.meta?.date && (
              <div><strong>Meeting Date:</strong> {selectedNode.meta.date}</div>
            )}

            {/* Verbatim Quote if available */}
            {selectedNode.meta?.verbatim_quote && (
              <div style={{ marginTop: 6 }}>
                <strong>Verbatim Quote:</strong>
                <blockquote className="ws-quote-box" style={{ marginTop: 4, marginInline: 0 }}>
                  "{selectedNode.meta.verbatim_quote}"
                </blockquote>
              </div>
            )}

            {/* Downstream & Upstream Connections */}
            <div style={{ marginTop: 10, borderTop: '1px solid rgba(13,13,12,0.1)', paddingTop: 10 }}>
              <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', color: 'rgba(13,13,12,0.5)', marginBottom: 6 }}>
                Connected Lineage Edges
              </div>
              {(rawGraph.edges || [])
                .filter((e) => e.source === selectedNode.id || e.target === selectedNode.id)
                .map((e, idx) => (
                  <div key={idx} style={{ fontSize: 11, padding: '3px 0' }}>
                    {e.source === selectedNode.id ? (
                      <span>→ <strong>{e.relation}</strong>: {layoutNodes[e.target]?.label || e.target}</span>
                    ) : (
                      <span>← <strong>{e.relation}</strong> from: {layoutNodes[e.source]?.label || e.source}</span>
                    )}
                  </div>
                ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
