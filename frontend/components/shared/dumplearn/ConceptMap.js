'use client'

import { useMemo, useState } from 'react'
import { forceSimulation, forceManyBody, forceLink, forceCenter, forceCollide } from 'd3-force'

// ─────────────────────────────────────────────────────────────────────────────
// The concept mind map — same physics-based auto-layout idea as Business's
// Mind canvas (mind/mindForceLayout.js: d3-force, settle, freeze), re-skinned
// for lesson concepts instead of memories. Rendered as SVG rather than raw
// canvas: a lesson's map is small (a handful of nodes) and interaction-heavy
// (click a node to jump to its concept block), so native DOM click targets
// and hover tooltips are simpler and more robust here than canvas hit-testing.
// ─────────────────────────────────────────────────────────────────────────────

const CREAM = '#F3EAD9'
const PALETTE = ['#ff9072', '#6fd6a8', '#7aa2ff', '#ffc266', '#c084fc', '#f472b6', '#5fd4d4']

function colorForCategory(category, categoryOrder) {
  const idx = Math.max(0, categoryOrder.indexOf(category))
  return PALETTE[idx % PALETTE.length]
}

function layout(rawNodes, rawEdges) {
  const nodes = rawNodes.map(n => ({ ...n }))
  const idSet = new Set(nodes.map(n => n.id))
  const links = rawEdges
    .filter(e => idSet.has(e.source) && idSet.has(e.target))
    .map(e => ({ ...e }))
  if (!nodes.length) return { nodes, links }
  const sim = forceSimulation(nodes)
    .force('charge', forceManyBody().strength(-220))
    .force('link', forceLink(links).id(d => d.id).distance(110))
    .force('center', forceCenter(0, 0))
    .force('collide', forceCollide(d => 22 + (d.weight || 0.5) * 22))
    .stop()
  for (let i = 0; i < 200; i++) sim.tick()
  return { nodes, links }
}

export default function ConceptMap({ mindMap, onNodeClick, activeId }) {
  const [hoveredEdge, setHoveredEdge] = useState(null)

  const { nodes, links, categories } = useMemo(() => {
    const rawNodes = mindMap?.nodes || []
    const rawEdges = mindMap?.edges || []
    const { nodes, links } = layout(rawNodes, rawEdges)
    const categories = [...new Set(rawNodes.map(n => n.category || 'general'))]
    return { nodes, links, categories }
  }, [mindMap])

  if (!nodes.length) return null

  const xs = nodes.map(n => n.x)
  const ys = nodes.map(n => n.y)
  const pad = 60
  const minX = Math.min(...xs) - pad
  const minY = Math.min(...ys) - pad
  const w = Math.max(240, Math.max(...xs) + pad - minX)
  const h = Math.max(240, Math.max(...ys) + pad - minY)
  const nodeById = new Map(nodes.map(n => [n.id, n]))

  return (
    <div style={{ width: '100%', overflow: 'auto', borderRadius: 16, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)' }}>
      <svg viewBox={`${minX} ${minY} ${w} ${h}`} width="100%" height={Math.min(460, h)} style={{ display: 'block' }}>
        {links.map((l, i) => {
          const a = nodeById.get(typeof l.source === 'object' ? l.source.id : l.source)
          const b = nodeById.get(typeof l.target === 'object' ? l.target.id : l.target)
          if (!a || !b) return null
          const mx = (a.x + b.x) / 2
          const my = (a.y + b.y) / 2
          return (
            <g key={i} onMouseEnter={() => setHoveredEdge(i)} onMouseLeave={() => setHoveredEdge(null)}>
              <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="rgba(243,234,217,0.18)" strokeWidth={1.5} />
              {hoveredEdge === i && l.label && (
                <text x={mx} y={my} textAnchor="middle" fontSize="10" fill={CREAM} style={{ paintOrder: 'stroke', stroke: '#1A1A1A', strokeWidth: 3 }}>
                  {l.label}
                </text>
              )}
            </g>
          )
        })}
        {nodes.map(n => {
          const r = 10 + (n.weight || 0.5) * 16
          const color = colorForCategory(n.category || 'general', categories)
          const active = activeId === n.id
          return (
            <g key={n.id} onClick={() => onNodeClick?.(n.id)} style={{ cursor: onNodeClick ? 'pointer' : 'default' }}>
              <circle
                cx={n.x} cy={n.y} r={r} fill={color} fillOpacity={active ? 0.95 : 0.55}
                stroke={active ? '#ffffff' : color} strokeWidth={active ? 2 : 0}
              />
              <text
                x={n.x} y={n.y + r + 13} textAnchor="middle" fontSize="11"
                fontWeight={active ? 700 : 500} fill={CREAM} style={{ pointerEvents: 'none' }}
              >
                {(n.label || '').slice(0, 24)}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
