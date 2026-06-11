import { forceSimulation, forceManyBody, forceLink, forceCenter, forceCollide } from 'd3-force'

const TICKS = 150

// Lays out memory nodes with d3-force, runs the simulation synchronously to
// settle, then stops it. Positions are frozen after this — idle drift/breathing
// is applied at render time instead of via continuous physics (keeps 60fps@800).
export function layoutMemoryNodes(nodes, edges) {
  const simNodes = nodes.map(n => ({ ...n }))
  const idSet = new Set(simNodes.map(n => n.id))
  const simLinks = edges
    .filter(e => idSet.has(e.source) && idSet.has(e.target))
    .map(e => ({ source: e.source, target: e.target, weight: e.weight ?? 0.5 }))

  if (simNodes.length === 0) return { nodes: simNodes, links: simLinks }

  const sim = forceSimulation(simNodes)
    .force('charge', forceManyBody().strength(-120))
    .force('link', forceLink(simLinks).id(d => d.id).distance(d => 140 - (d.weight ?? 0.5) * 80))
    .force('center', forceCenter(0, 0))
    .force('collide', forceCollide(d => 8 + (d.strength ?? 0) * 20))
    .stop()

  for (let i = 0; i < TICKS; i++) sim.tick()

  return { nodes: simNodes, links: simLinks }
}

// Positions a satellite node (gap or queue item) near the centroid of its
// related memory nodes, with a small deterministic offset so repeated
// layouts don't jitter between renders.
export function positionNearRelated(relatedIds, nodeById, seed, radius = 60) {
  const points = (relatedIds || [])
    .map(id => nodeById.get(id))
    .filter(Boolean)

  let cx = 0
  let cy = 0
  if (points.length > 0) {
    cx = points.reduce((s, p) => s + p.x, 0) / points.length
    cy = points.reduce((s, p) => s + p.y, 0) / points.length
  }

  // Deterministic pseudo-random angle/distance from the seed string
  let h = 0
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0
  const angle = (h % 360) * (Math.PI / 180)
  const dist = radius * (0.6 + ((h >> 8) % 100) / 100)

  return { x: cx + Math.cos(angle) * dist, y: cy + Math.sin(angle) * dist }
}

// Buckets nodes of the same cluster into grid-cell blobs for low-zoom LOD
// rendering. Computed once per layout (not per frame).
export function buildLODBlobs(nodes, cellSize = 70) {
  const buckets = new Map()
  for (const n of nodes) {
    const cx = Math.round(n.x / cellSize)
    const cy = Math.round(n.y / cellSize)
    const key = `${cx},${cy},${n.mind_category || 'general'}`
    let b = buckets.get(key)
    if (!b) {
      b = { x: 0, y: 0, count: 0, strength: 0, mind_category: n.mind_category || 'general', ids: [] }
      buckets.set(key, b)
    }
    b.x += n.x
    b.y += n.y
    b.count += 1
    b.strength += n.strength || 0
    b.ids.push(n.id)
  }
  return Array.from(buckets.values()).map(b => ({
    x: b.x / b.count,
    y: b.y / b.count,
    count: b.count,
    strength: b.strength / b.count,
    mind_category: b.mind_category,
    ids: b.ids,
  }))
}
