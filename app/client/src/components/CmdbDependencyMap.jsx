import React, { useCallback, useEffect, useMemo } from 'react'
import dagre from 'dagre'
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

const REL_LABELS = {
  depends_on: 'depends on',
  connected_to: 'connected to',
  assigned_to: 'assigned to',
  hosted_on: 'hosted on',
}

const EDGE_STROKE = {
  depends_on: '#be123c',
  connected_to: '#0d9488',
  assigned_to: '#7c3aed',
  hosted_on: '#ca8a04',
}

const NODE_W = 200
const NODE_H = 76

function CiNode({ data }) {
  return (
    <div className="rounded-xl border-2 border-teal-200 bg-white px-3 py-2 shadow-md min-w-[160px] max-w-[220px]">
      <Handle type="target" position={Position.Left} className="!bg-teal-500 !w-2.5 !h-2.5" />
      <div className="text-[10px] font-semibold text-teal-700 uppercase tracking-wide">{data.ciType}</div>
      <div className="text-sm font-bold text-slate-900 leading-snug line-clamp-2">{data.label}</div>
      <div className="text-[10px] font-mono text-slate-400 truncate mt-0.5" title={data.ciId}>
        {data.ciId}
      </div>
      <Handle type="source" position={Position.Right} className="!bg-teal-500 !w-2.5 !h-2.5" />
    </div>
  )
}

const nodeTypes = { ci: CiNode }

function layoutWithDagre(nodes, edges) {
  if (nodes.length === 0) return []
  const g = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}))
  g.setGraph({
    rankdir: 'LR',
    nodesep: 48,
    ranksep: 90,
    marginx: 24,
    marginy: 24,
  })
  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }))
  edges.forEach((e) => {
    if (g.hasNode(e.source) && g.hasNode(e.target)) {
      g.setEdge(e.source, e.target)
    }
  })
  dagre.layout(g)
  return nodes.map((n) => {
    const pos = g.node(n.id)
    if (!pos) {
      return { ...n, position: { x: 0, y: 0 } }
    }
    return {
      ...n,
      position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    }
  })
}

function buildElements(items, relationships) {
  const itemById = new Map(items.map((it) => [it.ci_id, it]))
  const idSet = new Set()
  for (const r of relationships) {
    idSet.add(r.source_ci)
    idSet.add(r.target_ci)
  }
  for (const it of items) {
    idSet.add(it.ci_id)
  }

  const nodes = [...idSet].map((id) => {
    const it = itemById.get(id)
    return {
      id,
      type: 'ci',
      data: {
        label: it?.name || id,
        ciType: it?.ci_type || 'CI',
        ciId: id,
      },
    }
  })

  const edges = relationships.map((r, i) => {
    const rt = r.relationship_type || ''
    const stroke = EDGE_STROKE[rt] || '#64748b'
    return {
      id: r.relationship_id || `rel-${i}`,
      source: r.source_ci,
      target: r.target_ci,
      type: 'smoothstep',
      animated: rt === 'depends_on',
      label: REL_LABELS[rt] || rt,
      style: { stroke, strokeWidth: 2 },
      markerEnd: { type: MarkerType.ArrowClosed, color: stroke, width: 18, height: 18 },
      labelStyle: { fill: '#1e293b', fontWeight: 600, fontSize: 11 },
      labelBgStyle: { fill: '#f8fafc', fillOpacity: 0.95 },
      labelBgPadding: [4, 6],
    }
  })

  const positioned = layoutWithDagre(nodes, edges)
  return { nodes: positioned, edges }
}

function FlowInner({ items, relationships }) {
  const { nodes: initialNodes, edges: initialEdges } = useMemo(
    () => buildElements(items, relationships),
    [items, relationships],
  )
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)
  const { fitView } = useReactFlow()

  useEffect(() => {
    setNodes(initialNodes)
    setEdges(initialEdges)
  }, [initialNodes, initialEdges, setNodes, setEdges])

  useEffect(() => {
    const t = requestAnimationFrame(() => {
      fitView({ padding: 0.15, duration: 280 })
    })
    return () => cancelAnimationFrame(t)
  }, [nodes, edges, fitView])

  const onInit = useCallback(
    (instance) => {
      instance.fitView({ padding: 0.15 })
    },
    [],
  )

  if (relationships.length === 0 && items.length === 0) {
    return (
      <div className="flex h-[420px] items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50 text-sm text-slate-500">
        Add configuration items and relationships to see the dependency map.
      </div>
    )
  }

  if (relationships.length === 0) {
    return (
      <div className="flex h-[420px] items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50 text-sm text-slate-500">
        No relationships yet — the map needs at least one edge between CIs.
      </div>
    )
  }

  return (
    <div className="h-[min(520px,70vh)] min-h-[360px] w-full rounded-2xl border border-slate-200 overflow-hidden bg-slate-50">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        onInit={onInit}
        fitView
        minZoom={0.15}
        maxZoom={1.5}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={16} color="#cbd5e1" size={1} />
        <Controls className="!rounded-xl !border-slate-200 !shadow-sm" />
        <MiniMap
          className="!rounded-xl !border-slate-200"
          nodeColor={() => '#99f6e4'}
          maskColor="rgb(15 23 42 / 0.08)"
        />
      </ReactFlow>
    </div>
  )
}

/**
 * Directed dependency / relationship map for CMDB (React Flow + Dagre).
 */
export default function CmdbDependencyMap({ items, relationships }) {
  return (
    <ReactFlowProvider>
      <FlowInner items={items} relationships={relationships} />
    </ReactFlowProvider>
  )
}
