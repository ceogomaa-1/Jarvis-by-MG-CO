'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { layoutMemoryNodes, positionNearRelated, buildLODBlobs } from './mindForceLayout'
import { buildStars, drawStars } from './starfield'
import { colorForCategory, MIND_LABELS, GOLD } from './colors'
import {
  drawEdge, drawSynapseArc, drawNode, drawGapNode, drawQueueNode, drawBlob,
  hitTest, REMOVE_DURATION, LIGHT_DURATION,
} from './mindRender'
import NodeCard from './NodeCard'
import MindChatDock from './MindChatDock'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'
const MOBILE_BREAKPOINT = 768
const MIN_ZOOM = 0.15
const MAX_ZOOM = 3.5
const LOD_NODE_THRESHOLD = 150
const LOD_ZOOM_THRESHOLD = 0.55
const REPLAY_DURATION = 1500

async function fetchJSON(url, fallback, opts) {
  try {
    const res = await fetch(url, opts)
    if (!res.ok) return fallback
    return await res.json()
  } catch {
    return fallback
  }
}

function makeStateRef() {
  return {
    nodes: [], nodeById: new Map(), links: [],
    gapNodes: [], queueNodes: [], synapseArcs: [],
    stars: [], pan: { x: 0, y: 0 }, zoom: 1,
    width: 0, height: 0, dpr: 1,
    hovered: null, focusedId: null,
    pointer: { down: false, dragging: false, lastX: 0, lastY: 0, startX: 0, startY: 0 },
    replay: null, lodBlobs: null, isMobile: false, pendingRemoval: [],
    worldToScreen: (x, y) => ({ x, y }),
    screenToWorld: (x, y) => ({ x, y }),
  }
}

export default function MindCanvas({ userId }) {
  const containerRef = useRef(null)
  const canvasRef = useRef(null)
  const rafRef = useRef(null)
  const stateRef = useRef(null)
  if (!stateRef.current) stateRef.current = makeStateRef()

  const [loading, setLoading] = useState(true)
  const [nodeCount, setNodeCount] = useState(0)
  const [focusedNode, setFocusedNode] = useState(null)
  const [findingSynapses, setFindingSynapses] = useState(false)
  const [synapseMsg, setSynapseMsg] = useState(null)
  const [isMobile, setIsMobile] = useState(false)

  // Track viewport size for legend/UI (separate from the canvas's own resize loop).
  useEffect(() => {
    const check = () => {
      const mobile = window.innerWidth < MOBILE_BREAKPOINT
      setIsMobile(mobile)
      stateRef.current.isMobile = mobile
    }
    check()
    window.addEventListener('resize', check)
    return () => window.removeEventListener('resize', check)
  }, [])

  useEffect(() => {
    stateRef.current.focusedId = focusedNode?.id ?? null
  }, [focusedNode])

  const applyGraph = useCallback((graph, gaps, synapses) => {
    const { nodes, links } = layoutMemoryNodes(graph.nodes || [], graph.edges || [])
    const nodeById = new Map(nodes.map(n => [n.id, n]))

    const gapNodes = (gaps || []).map(g => {
      const related = nodes.filter(n => n.mind_category === g.mind_category).map(n => n.id)
      const seedIds = related.length ? related : nodes.map(n => n.id)
      const pos = positionNearRelated(seedIds, nodeById, g.id, 100)
      return { ...g, type: 'gap', x: pos.x, y: pos.y }
    })

    const queueNodes = (graph.queue_nodes || []).map(q => {
      const pos = positionNearRelated(q.source_memory_ids || [], nodeById, q.id, 50)
      return { ...q, x: pos.x, y: pos.y }
    })

    const synapseArcs = (synapses || [])
      .map(s => ({ synapse: s, a: nodeById.get(s.memory_a_id), b: nodeById.get(s.memory_b_id) }))
      .filter(s => s.a && s.b)

    const st = stateRef.current
    st.nodes = nodes
    st.nodeById = nodeById
    st.links = links
    st.gapNodes = gapNodes
    st.queueNodes = queueNodes
    st.synapseArcs = synapseArcs
    st.lodBlobs = nodes.length > LOD_NODE_THRESHOLD ? buildLODBlobs(nodes) : null
  }, [])

  const scheduleReplay = useCallback(async (uid) => {
    const since = new Date(Date.now() - 24 * 3600 * 1000).toISOString()
    const data = await fetchJSON(
      `${BACKEND}/api/business/mind/activity?user_id=${encodeURIComponent(uid)}&since=${encodeURIComponent(since)}`,
      { activity: [] }
    )
    const events = data.activity || []
    if (!events.length) return
    stateRef.current.replay = { events, startTime: performance.now(), duration: REPLAY_DURATION, processed: 0 }
  }, [])

  // Data load
  useEffect(() => {
    if (!userId) return
    let cancelled = false

    async function load() {
      setLoading(true)
      const mobile = typeof window !== 'undefined' && window.innerWidth < MOBILE_BREAKPOINT
      stateRef.current.isMobile = mobile
      const limit = mobile ? 300 : 800

      const [graph, gapsRes, synRes] = await Promise.all([
        fetchJSON(`${BACKEND}/api/business/mind/graph?user_id=${encodeURIComponent(userId)}&limit=${limit}`, { nodes: [], edges: [], queue_nodes: [] }),
        fetchJSON(`${BACKEND}/api/business/mind/gaps?user_id=${encodeURIComponent(userId)}`, { gaps: [] }),
        fetchJSON(`${BACKEND}/api/business/mind/synapses?user_id=${encodeURIComponent(userId)}`, { synapses: [] }),
      ])
      if (cancelled) return

      applyGraph(graph, gapsRes.gaps || [], synRes.synapses || [])
      setNodeCount((graph.nodes || []).length)
      setLoading(false)
      scheduleReplay(userId)
    }

    load()
    return () => { cancelled = true }
  }, [userId, applyGraph, scheduleReplay])

  // Canvas setup + render loop (mounts once)
  useEffect(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return
    const ctx = canvas.getContext('2d')
    const st = stateRef.current
    st.stars = buildStars(st.isMobile)

    let cancelled = false

    function resize() {
      const rect = container.getBoundingClientRect()
      st.width = rect.width
      st.height = rect.height
      st.dpr = Math.min(window.devicePixelRatio || 1, 2)
      canvas.width = Math.round(st.width * st.dpr)
      canvas.height = Math.round(st.height * st.dpr)
      canvas.style.width = `${st.width}px`
      canvas.style.height = `${st.height}px`
      ctx.setTransform(st.dpr, 0, 0, st.dpr, 0, 0)
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(container)

    st.worldToScreen = (x, y) => ({
      x: st.width / 2 + (x - st.pan.x) * st.zoom,
      y: st.height / 2 + (y - st.pan.y) * st.zoom,
    })
    st.screenToWorld = (x, y) => ({
      x: st.pan.x + (x - st.width / 2) / st.zoom,
      y: st.pan.y + (y - st.height / 2) / st.zoom,
    })

    function processReplay(now) {
      const r = st.replay
      if (!r) return
      const elapsed = now - r.startTime
      const progress = Math.min(1, elapsed / r.duration)
      const eventCount = Math.floor(progress * r.events.length)
      for (let i = r.processed; i < eventCount; i++) {
        const ev = r.events[i]
        const node = st.nodeById.get(ev.memory_id)
        if (node) {
          node.litUntil = now + 700
          if (ev.event_type === 'born' && !node._replayedBorn) {
            node.spawnedAt = now
            node._replayedBorn = true
          }
        }
      }
      r.processed = eventCount
      if (progress >= 1) st.replay = null
    }

    function cleanupRemovedNodes(now) {
      if (!st.pendingRemoval.length) return
      const remaining = []
      let changed = false
      for (const id of st.pendingRemoval) {
        const node = st.nodeById.get(id)
        if (!node) continue
        if (now - node.removingAt >= REMOVE_DURATION) {
          st.nodes = st.nodes.filter(n => n.id !== id)
          st.nodeById.delete(id)
          st.links = st.links.filter(l => l.source.id !== id && l.target.id !== id)
          st.synapseArcs = st.synapseArcs.filter(a => a.a.id !== id && a.b.id !== id)
          changed = true
        } else {
          remaining.push(id)
        }
      }
      st.pendingRemoval = remaining
      if (changed) setNodeCount(st.nodes.length)
    }

    function frame(now) {
      if (cancelled) return
      const t = now / 1000
      const w2s = st.worldToScreen
      const focusedId = st.focusedId

      ctx.clearRect(0, 0, st.width, st.height)
      drawStars(ctx, st.stars, st.width, st.height, st.pan)

      const useLOD = !!(st.lodBlobs && st.zoom < LOD_ZOOM_THRESHOLD)

      if (!useLOD) {
        for (const link of st.links) {
          const dimmed = !!(focusedId && link.source.id !== focusedId && link.target.id !== focusedId)
          drawEdge(ctx, link, w2s, dimmed)
        }
      }

      for (const arc of st.synapseArcs) {
        const focused = focusedId === arc.synapse.id
        drawSynapseArc(ctx, arc, w2s, t, { focused, dimmed: !!(focusedId && !focused) })
      }

      if (useLOD) {
        for (const blob of st.lodBlobs) {
          drawBlob(ctx, blob, w2s, st.zoom, {})
        }
      } else {
        for (const node of st.nodes) {
          drawNode(ctx, node, w2s, st.zoom, t, {
            hovered: st.hovered === node,
            focused: focusedId === node.id,
            dimmed: !!(focusedId && focusedId !== node.id),
          })
        }
      }

      for (const gap of st.gapNodes) {
        drawGapNode(ctx, gap, w2s, st.zoom, t, {
          hovered: st.hovered === gap,
          focused: focusedId === gap.id,
          dimmed: !!(focusedId && focusedId !== gap.id),
        })
      }

      for (const q of st.queueNodes) {
        drawQueueNode(ctx, q, w2s, st.zoom, t, {
          focused: focusedId === q.id,
          dimmed: !!(focusedId && focusedId !== q.id),
        })
      }

      processReplay(now)
      cleanupRemovedNodes(now)

      rafRef.current = requestAnimationFrame(frame)
    }
    rafRef.current = requestAnimationFrame(frame)

    function onWheel(e) {
      e.preventDefault()
      if (!st.width) return
      const rect = canvas.getBoundingClientRect()
      const mx = e.clientX - rect.left
      const my = e.clientY - rect.top
      const before = st.screenToWorld(mx, my)
      const factor = Math.exp(-e.deltaY * 0.001)
      st.zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, st.zoom * factor))
      const after = st.screenToWorld(mx, my)
      st.pan.x += before.x - after.x
      st.pan.y += before.y - after.y
    }
    canvas.addEventListener('wheel', onWheel, { passive: false })

    return () => {
      cancelled = true
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      ro.disconnect()
      canvas.removeEventListener('wheel', onWheel)
    }
  }, [])

  function buildCardData(hit) {
    const st = stateRef.current
    if (hit.type === 'memory') {
      const relatedIds = new Set()
      for (const link of st.links) {
        if (link.source.id === hit.id) relatedIds.add(link.target.id)
        else if (link.target.id === hit.id) relatedIds.add(link.source.id)
      }
      const related = [...relatedIds].slice(0, 5).map(id => st.nodeById.get(id)).filter(Boolean)
      return { ...hit, _related: related }
    }
    return hit
  }

  function onPointerDown(e) {
    const st = stateRef.current
    st.pointer.down = true
    st.pointer.dragging = false
    st.pointer.lastX = e.clientX
    st.pointer.lastY = e.clientY
    st.pointer.startX = e.clientX
    st.pointer.startY = e.clientY
    e.currentTarget.setPointerCapture(e.pointerId)
  }

  function onPointerMove(e) {
    const st = stateRef.current
    if (!st.width) return
    const rect = e.currentTarget.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top

    if (st.pointer.down) {
      const dx = e.clientX - st.pointer.lastX
      const dy = e.clientY - st.pointer.lastY
      if (!st.pointer.dragging && (Math.abs(e.clientX - st.pointer.startX) > 3 || Math.abs(e.clientY - st.pointer.startY) > 3)) {
        st.pointer.dragging = true
      }
      if (st.pointer.dragging) {
        st.pan.x -= dx / st.zoom
        st.pan.y -= dy / st.zoom
        st.hovered = null
        e.currentTarget.style.cursor = 'grabbing'
      }
      st.pointer.lastX = e.clientX
      st.pointer.lastY = e.clientY
      return
    }

    const hit = hitTest(st, mx, my)
    st.hovered = hit
    e.currentTarget.style.cursor = hit ? 'pointer' : 'grab'
  }

  function onPointerUp(e) {
    const st = stateRef.current
    const wasDragging = st.pointer.dragging
    st.pointer.down = false
    st.pointer.dragging = false
    try { e.currentTarget.releasePointerCapture(e.pointerId) } catch { /* noop */ }
    e.currentTarget.style.cursor = 'grab'
    if (wasDragging) return

    const rect = e.currentTarget.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top
    const hit = hitTest(st, mx, my)
    setFocusedNode(hit ? buildCardData(hit) : null)
  }

  function onPointerLeave() {
    stateRef.current.hovered = null
  }

  const handleForget = useCallback(async (nodeId) => {
    if (userId) {
      try {
        await fetch(`${BACKEND}/api/business/mind/memories/${encodeURIComponent(nodeId)}?user_id=${encodeURIComponent(userId)}`, { method: 'DELETE' })
      } catch { /* best-effort */ }
    }
    const st = stateRef.current
    const node = st.nodeById.get(nodeId)
    if (node) {
      node.removingAt = performance.now()
      st.pendingRemoval.push(nodeId)
    }
    setFocusedNode(null)
  }, [userId])

  const lightUpUsed = useCallback((ids) => {
    const st = stateRef.current
    const now = performance.now()
    for (const id of ids || []) {
      const node = st.nodeById.get(id)
      if (node) node.litUntil = now + LIGHT_DURATION
    }
  }, [])

  const lightUpBorn = useCallback((memories) => {
    const st = stateRef.current
    const now = performance.now()
    let added = false
    for (const m of memories || []) {
      if (!m.id || st.nodeById.has(m.id)) continue
      const usedNodes = st.nodes.filter(n => n.litUntil && n.litUntil > now)
      let cx = 0
      let cy = 0
      if (usedNodes.length) {
        cx = usedNodes.reduce((s, n) => s + n.x, 0) / usedNodes.length
        cy = usedNodes.reduce((s, n) => s + n.y, 0) / usedNodes.length
      }
      const angle = Math.random() * Math.PI * 2
      const dist = 30 + Math.random() * 50
      const newNode = {
        id: m.id,
        type: 'memory',
        memory: m.memory,
        mind_category: m.mind_category || 'general',
        source: 'chat',
        created_at: new Date().toISOString(),
        strength: 0.25,
        x: cx + Math.cos(angle) * dist,
        y: cy + Math.sin(angle) * dist,
        spawnedAt: now,
        litUntil: now + LIGHT_DURATION,
      }
      st.nodes.push(newNode)
      st.nodeById.set(newNode.id, newNode)
      added = true
    }
    if (added) {
      const st2 = stateRef.current
      st2.lodBlobs = st2.nodes.length > LOD_NODE_THRESHOLD ? buildLODBlobs(st2.nodes) : null
      setNodeCount(st2.nodes.length)
    }
  }, [])

  const handleFindSynapses = useCallback(async () => {
    if (!userId || findingSynapses) return
    setFindingSynapses(true)
    setSynapseMsg(null)
    try {
      const res = await fetch(`${BACKEND}/api/business/mind/synapses/generate?user_id=${encodeURIComponent(userId)}`, { method: 'POST' })
      const data = await res.json()
      if (data.rate_limited) {
        setSynapseMsg('Already searched today')
      } else {
        const created = data.synapses || []
        if (created.length) {
          const st = stateRef.current
          for (const s of created) {
            const a = st.nodeById.get(s.memory_a_id)
            const b = st.nodeById.get(s.memory_b_id)
            if (a && b) st.synapseArcs.push({ synapse: s, a, b })
          }
          setSynapseMsg(`Found ${created.length} connection${created.length > 1 ? 's' : ''}`)
        } else {
          setSynapseMsg('No new connections found')
        }
      }
    } catch {
      setSynapseMsg('Search failed')
    }
    setFindingSynapses(false)
    setTimeout(() => setSynapseMsg(null), 4000)
  }, [userId, findingSynapses])

  return (
    <div
      ref={containerRef}
      style={{ position: 'relative', flex: '1 1 auto', minHeight: 0, overflow: 'hidden', background: '#131313' }}
    >
      <canvas
        ref={canvasRef}
        style={{ display: 'block', width: '100%', height: '100%', touchAction: 'none', cursor: 'grab' }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={onPointerLeave}
      />

      {loading && (
        <div style={{
          position: 'absolute', inset: 0, display: 'flex',
          alignItems: 'center', justifyContent: 'center', pointerEvents: 'none',
        }}>
          <div style={{
            fontFamily: 'var(--pixel)', fontSize: 11, letterSpacing: '0.2em',
            color: '#6e6e6e', textTransform: 'uppercase',
          }}>
            Loading your Mind...
          </div>
        </div>
      )}

      {!loading && nodeCount === 0 && (
        <div style={{
          position: 'absolute', inset: 0, display: 'flex',
          alignItems: 'center', justifyContent: 'center', pointerEvents: 'none',
          textAlign: 'center', padding: 24,
        }}>
          <div style={{
            fontFamily: 'var(--pixel)', fontSize: 12, letterSpacing: '0.15em',
            color: '#6e6e6e', lineHeight: 2.4, textTransform: 'uppercase',
          }}>
            Your Mind is still forming.<br />Talk to Jarvis to begin.
          </div>
        </div>
      )}

      {/* Memory count */}
      <div style={{
        position: 'absolute', top: 16, left: 16,
        fontFamily: 'var(--pixel)', fontSize: 10, letterSpacing: '0.15em',
        color: '#6e6e6e', textTransform: 'uppercase', pointerEvents: 'none',
      }}>
        {nodeCount} {nodeCount === 1 ? 'memory' : 'memories'}
      </div>

      {/* Find synapses */}
      <div style={{ position: 'absolute', top: 16, right: 16, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
        <button
          onClick={handleFindSynapses}
          disabled={findingSynapses || !userId}
          style={{
            fontFamily: 'var(--pixel)', fontSize: 10, letterSpacing: '0.15em',
            padding: '7px 14px', textTransform: 'uppercase',
            background: 'rgba(255,210,74,0.06)',
            color: findingSynapses ? '#6e6e6e' : GOLD,
            border: `1px solid ${findingSynapses ? 'rgba(232,232,232,0.12)' : 'rgba(255,210,74,0.4)'}`,
            borderRadius: 4, cursor: findingSynapses ? 'default' : 'pointer',
            boxShadow: findingSynapses ? 'none' : `0 0 14px rgba(255,210,74,0.18)`,
            transition: 'all 0.2s ease',
          }}
        >
          {findingSynapses ? 'Searching...' : '✦ Find synapses'}
        </button>
        {synapseMsg && (
          <div style={{
            fontFamily: 'var(--pixel)', fontSize: 9, letterSpacing: '0.1em',
            color: '#6e6e6e', textTransform: 'uppercase',
          }}>
            {synapseMsg}
          </div>
        )}
      </div>

      {/* Cluster legend */}
      {!isMobile && (
        <div style={{ position: 'absolute', bottom: 16, left: 16, display: 'flex', flexDirection: 'column', gap: 5, pointerEvents: 'none' }}>
          {Object.entries(MIND_LABELS).map(([key, label]) => (
            <div key={key} style={{
              display: 'flex', alignItems: 'center', gap: 8,
              fontSize: 9, fontFamily: 'var(--pixel)', letterSpacing: '0.1em',
              color: '#6e6e6e', textTransform: 'uppercase',
            }}>
              <span style={{
                width: 7, height: 7, display: 'inline-block',
                background: colorForCategory(key),
                boxShadow: `0 0 6px ${colorForCategory(key)}`,
              }} />
              {label}
            </div>
          ))}
        </div>
      )}

      <NodeCard
        node={focusedNode}
        userId={userId}
        onClose={() => setFocusedNode(null)}
        onForget={handleForget}
      />

      <MindChatDock userId={userId} onMemoryUsed={lightUpUsed} onMemoryBorn={lightUpBorn} />
    </div>
  )
}
