'use client'
import { useCallback, useMemo, useState, useEffect, useRef } from 'react'
import {
  ReactFlow, Background, Controls,
  useNodesState, useEdgesState,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useRouter } from 'next/navigation'
import { motion, AnimatePresence } from 'framer-motion'
import { Zap, Sparkles } from 'lucide-react'

import { AGENTS, getOrbitPosition } from '../../lib/business/workflow/agentRegistry'
import JarvisCenterNode from './workflow/JarvisCenterNode'
import AgentNode from './workflow/AgentNode'
import AgentInspectorPanel from './workflow/AgentInspectorPanel'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

// Agent IDs for the 4-cycle operator pipeline (in execution order)
const OPERATOR_STAGES = [
  'operator-strategist',
  'operator-researcher',
  'operator-creator',
  'operator-packager',
]

const nodeTypes = {
  jarvisCenter: JarvisCenterNode,
  agentNode: AgentNode,
}

const ORBIT_RADIUS = 340

function buildInitialNodes() {
  const centerNode = {
    id: 'jarvis-center',
    type: 'jarvisCenter',
    position: { x: 0, y: 0 },
    origin: [0.5, 0.5],
    data: {},
    draggable: false,
  }

  const agentNodes = AGENTS.map((agent, i) => {
    const { x, y } = getOrbitPosition(i, AGENTS.length, ORBIT_RADIUS)
    return {
      id: agent.id,
      type: 'agentNode',
      position: { x, y },
      origin: [0.5, 0.5],
      data: { agent },
      draggable: false,
    }
  })

  return [centerNode, ...agentNodes]
}

function buildInitialEdges() {
  return AGENTS.map((agent) => ({
    id: `e-center-${agent.id}`,
    source: 'jarvis-center',
    target: agent.id,
    type: 'smoothstep',
    style: { stroke: 'rgba(243,234,217,0.2)', strokeWidth: 1 },
    animated: true,
  }))
}

// ── Control panel ─────────────────────────────────────────────────────────────
function CanvasControlPanel({ onTriggerOperator, onTriggerCreation, isRunning }) {
  return (
    <div style={{
      position: 'absolute', bottom: 36, left: '50%',
      transform: 'translateX(-50%)',
      display: 'flex', alignItems: 'center', gap: 10,
      zIndex: 20, pointerEvents: 'auto',
    }}>
      <motion.button
        whileHover={!isRunning ? { scale: 1.04 } : {}}
        whileTap={!isRunning ? { scale: 0.96 } : {}}
        onClick={onTriggerOperator}
        disabled={isRunning}
        style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '10px 22px', borderRadius: 12,
          border: 'none', cursor: isRunning ? 'not-allowed' : 'pointer',
          background: isRunning ? 'rgba(243,234,217,0.05)' : '#c84b31',
          color: isRunning ? 'rgba(243,234,217,0.28)' : '#0a0a0a',
          fontFamily: 'var(--font-arcade), monospace',
          fontSize: 8, letterSpacing: '0.1em', textTransform: 'uppercase',
          boxShadow: isRunning ? 'none' : '0 0 28px rgba(200,75,49,0.28)',
          transition: 'all 300ms ease',
        }}
      >
        <Zap size={13} />
        {isRunning ? 'Operator Running…' : 'Run Operator Now'}
      </motion.button>

      <motion.button
        whileHover={{ scale: 1.04 }}
        whileTap={{ scale: 0.96 }}
        onClick={onTriggerCreation}
        style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '10px 22px', borderRadius: 12,
          background: 'rgba(243,234,217,0.04)',
          border: '1px solid rgba(243,234,217,0.1)',
          cursor: 'pointer',
          color: 'rgba(243,234,217,0.6)',
          fontFamily: 'var(--font-arcade), monospace',
          fontSize: 8, letterSpacing: '0.1em', textTransform: 'uppercase',
          transition: 'all 200ms ease',
        }}
        onMouseEnter={e => { e.currentTarget.style.color = 'rgba(243,234,217,0.9)'; e.currentTarget.style.background = 'rgba(243,234,217,0.08)' }}
        onMouseLeave={e => { e.currentTarget.style.color = 'rgba(243,234,217,0.6)'; e.currentTarget.style.background = 'rgba(243,234,217,0.04)' }}
      >
        <Sparkles size={13} />
        Create Task
      </motion.button>
    </div>
  )
}

// ── Creation task modal ───────────────────────────────────────────────────────
function CreationTaskModal({ onClose, onSubmit }) {
  const [taskDescription, setTaskDescription] = useState('')

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(10px)',
      }}
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 6 }}
        transition={{ duration: 0.22, ease: 'easeOut' }}
        onClick={e => e.stopPropagation()}
        style={{
          width: '100%', maxWidth: 520,
          margin: '0 20px',
          background: 'rgba(12,12,15,0.92)',
          backdropFilter: 'blur(28px)',
          border: '1px solid rgba(243,234,217,0.12)',
          borderRadius: 18, padding: 28,
          fontFamily: 'system-ui, sans-serif',
          boxShadow: '0 30px 70px rgba(0,0,0,0.55)',
        }}
      >
        <div style={{
          fontFamily: 'var(--font-arcade), monospace',
          fontSize: 9, letterSpacing: '0.12em',
          color: '#f3ead9', textTransform: 'uppercase', marginBottom: 6,
        }}>
          Create Task
        </div>
        <p style={{ fontSize: 12, color: 'rgba(243,234,217,0.42)', lineHeight: 1.65, marginBottom: 16 }}>
          Describe what you want Jarvis to create. The Creation 1.0 team (Strategist, Copywriter, Designer, Researcher, Analyst, Reporter) will work on it.
        </p>
        <textarea
          value={taskDescription}
          onChange={e => setTaskDescription(e.target.value)}
          placeholder="e.g. Create a sales email sequence for restaurant owners…"
          autoFocus
          rows={4}
          style={{
            width: '100%', boxSizing: 'border-box',
            background: 'rgba(243,234,217,0.03)',
            border: '1px solid rgba(243,234,217,0.1)',
            borderRadius: 10, padding: '10px 13px',
            color: '#f3ead9', fontSize: 13, lineHeight: 1.6,
            fontFamily: 'system-ui, sans-serif',
            resize: 'none', outline: 'none',
            transition: 'border-color 200ms',
          }}
          onFocus={e => { e.target.style.borderColor = 'rgba(243,234,217,0.22)' }}
          onBlur={e => { e.target.style.borderColor = 'rgba(243,234,217,0.1)' }}
          onKeyDown={e => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && taskDescription.trim()) {
              onSubmit(taskDescription)
              onClose()
            }
          }}
        />
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 16 }}>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: '1px solid rgba(243,234,217,0.1)',
              borderRadius: 9, padding: '8px 16px',
              color: 'rgba(243,234,217,0.5)', fontSize: 11,
              fontFamily: 'system-ui', cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={() => { if (taskDescription.trim()) { onSubmit(taskDescription); onClose() } }}
            disabled={!taskDescription.trim()}
            style={{
              background: taskDescription.trim() ? '#c84b31' : 'rgba(200,75,49,0.2)',
              border: 'none', borderRadius: 9, padding: '8px 20px',
              color: taskDescription.trim() ? '#0a0a0a' : 'rgba(243,234,217,0.25)',
              fontSize: 11, fontWeight: 500,
              fontFamily: 'system-ui',
              cursor: taskDescription.trim() ? 'pointer' : 'not-allowed',
              transition: 'all 200ms',
            }}
          >
            Launch Creation
          </button>
        </div>
      </motion.div>
    </div>
  )
}

// ── Main canvas ───────────────────────────────────────────────────────────────
export default function WorkflowCanvas({ userId }) {
  const router = useRouter()
  const [nodes, setNodes, onNodesChange] = useNodesState(useMemo(buildInitialNodes, []))
  const [edges, , onEdgesChange] = useEdgesState(useMemo(buildInitialEdges, []))
  const [selectedAgent, setSelectedAgent] = useState(null)
  const [agentActivity, setAgentActivity] = useState({})
  const [activityLoading, setActivityLoading] = useState(false)
  const [liveStatuses, setLiveStatuses] = useState({})
  const [isRunning, setIsRunning] = useState(false)
  const [showCreationModal, setShowCreationModal] = useState(false)
  const esRef = useRef(null)

  // ── Activity fetch (called on mount + after a run completes) ──────────────
  const fetchActivity = useCallback(() => {
    if (!userId) return
    setActivityLoading(true)
    fetch(`${BACKEND}/api/business/agents/activity?user_id=${encodeURIComponent(userId)}`)
      .then(r => r.json())
      .then(data => {
        const activity = data.agents || {}
        setAgentActivity(activity)
        setNodes(prev => prev.map(n => {
          if (n.id === 'jarvis-center') return n
          const a = activity[n.id]
          if (!a) return n
          return {
            ...n,
            data: { ...n.data, agent: { ...n.data.agent, status: a.status || 'idle' } },
          }
        }))
      })
      .catch(() => {})
      .finally(() => setActivityLoading(false))
  }, [userId]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    fetchActivity()
  }, [userId]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Apply live statuses to React Flow nodes ──────────────────────────────
  useEffect(() => {
    if (Object.keys(liveStatuses).length === 0) return
    setNodes(prev => prev.map(n => {
      if (n.id === 'jarvis-center') return n
      const ls = liveStatuses[n.id]
      if (ls === undefined) return n
      return {
        ...n,
        data: { ...n.data, agent: { ...n.data.agent, status: ls } },
      }
    }))
  }, [liveStatuses]) // eslint-disable-line react-hooks/exhaustive-deps

  // Cleanup SSE on unmount
  useEffect(() => {
    return () => { esRef.current?.close() }
  }, [])

  // ── Trigger operator run ─────────────────────────────────────────────────
  async function handleTriggerOperator() {
    if (!userId || isRunning) return
    setIsRunning(true)

    // Reset all operator agents to idle immediately
    const resetStatuses = {}
    OPERATOR_STAGES.forEach(id => { resetStatuses[id] = 'idle' })
    setLiveStatuses(resetStatuses)

    try {
      const res = await fetch(`${BACKEND}/api/business/operator/trigger`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId }),
      })
      const data = await res.json()
      const runId = data.run_id
      if (!runId) { setIsRunning(false); return }

      // Subscribe to SSE status stream
      const es = new EventSource(
        `${BACKEND}/api/business/operator/status/stream?run_id=${encodeURIComponent(runId)}&user_id=${encodeURIComponent(userId)}`
      )
      esRef.current = es

      es.onmessage = (event) => {
        try {
          const { stage, cycles_completed, status } = JSON.parse(event.data)
          const cycleNum = cycles_completed || 0

          setLiveStatuses(() => {
            const updated = {}
            OPERATOR_STAGES.forEach(id => { updated[id] = 'idle' })
            // Mark completed stages as done
            OPERATOR_STAGES.slice(0, cycleNum).forEach(id => { updated[id] = 'done' })
            // Current stage is active (while still running)
            if (status === 'running' && stage && OPERATOR_STAGES.includes(stage)) {
              updated[stage] = 'active'
            }
            if (status === 'complete') {
              OPERATOR_STAGES.forEach(id => { updated[id] = 'done' })
            }
            if (status === 'failed') {
              const activeStage = OPERATOR_STAGES[cycleNum]
              if (activeStage) updated[activeStage] = 'error'
            }
            return updated
          })

          if (status !== 'running') {
            es.close()
            esRef.current = null
            setIsRunning(false)
            // Refresh inspector activity after run settles
            setTimeout(fetchActivity, 1500)
          }
        } catch {}
      }

      es.onerror = () => {
        es.close()
        esRef.current = null
        setIsRunning(false)
      }
    } catch (e) {
      console.error('Trigger operator failed:', e)
      setIsRunning(false)
    }
  }

  // ── Launch creation task → prefill chat ──────────────────────────────────
  function handleCreationTask(description) {
    if (!description.trim()) return
    sessionStorage.setItem('jarvis_prefill', `Create: ${description}`)
    router.push('/business/chat')
  }

  const onNodeClick = useCallback((_, node) => {
    if (node.id === 'jarvis-center') return
    setSelectedAgent(node.data.agent)
  }, [])

  return (
    <div style={{ width: '100%', height: 'calc(100vh - 56px)', background: '#0a0908', position: 'relative' }}>
      <style>{`
        .react-flow__controls {
          background: rgba(15,15,18,0.65) !important;
          backdrop-filter: blur(20px) !important;
          border: 1px solid rgba(243,234,217,0.12) !important;
          border-radius: 10px !important;
          box-shadow: none !important;
        }
        .react-flow__controls-button {
          background: transparent !important;
          border: none !important;
          border-bottom: 1px solid rgba(243,234,217,0.07) !important;
          color: rgba(243,234,217,0.7) !important;
          fill: rgba(243,234,217,0.7) !important;
        }
        .react-flow__controls-button:hover {
          background: rgba(243,234,217,0.06) !important;
        }
        .react-flow__controls-button:last-child {
          border-bottom: none !important;
        }
        .react-flow__edge-path { stroke-dasharray: 4 6 !important; }
      `}</style>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        nodeTypes={nodeTypes}
        fitView
        defaultViewport={{ x: 0, y: 0, zoom: 0.85 }}
        minZoom={0.4}
        maxZoom={1.5}
        proOptions={{ hideAttribution: true }}
        style={{ background: '#0a0908' }}
      >
        <Background
          variant="dots"
          gap={32}
          size={1.2}
          color="rgba(243,234,217,0.06)"
        />
        <Controls position="bottom-left" />
      </ReactFlow>

      {/* Control panel */}
      <CanvasControlPanel
        onTriggerOperator={handleTriggerOperator}
        onTriggerCreation={() => setShowCreationModal(true)}
        isRunning={isRunning}
      />

      {/* Creation task modal */}
      <AnimatePresence>
        {showCreationModal && (
          <CreationTaskModal
            onClose={() => setShowCreationModal(false)}
            onSubmit={handleCreationTask}
          />
        )}
      </AnimatePresence>

      <AgentInspectorPanel
        agent={selectedAgent}
        agentActivity={agentActivity[selectedAgent?.id]}
        activityLoading={activityLoading}
        onClose={() => setSelectedAgent(null)}
      />
    </div>
  )
}
