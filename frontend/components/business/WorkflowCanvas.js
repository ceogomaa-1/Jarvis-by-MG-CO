'use client'
import { useCallback, useMemo, useState, useEffect } from 'react'
import {
  ReactFlow, Background, Controls,
  useNodesState, useEdgesState,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import { AGENTS, getOrbitPosition } from '../../lib/business/workflow/agentRegistry'
import JarvisCenterNode from './workflow/JarvisCenterNode'
import AgentNode from './workflow/AgentNode'
import AgentInspectorPanel from './workflow/AgentInspectorPanel'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

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

export default function WorkflowCanvas({ userId }) {
  const [nodes, setNodes, onNodesChange] = useNodesState(useMemo(buildInitialNodes, []))
  const [edges, , onEdgesChange] = useEdgesState(useMemo(buildInitialEdges, []))
  const [selectedAgent, setSelectedAgent] = useState(null)
  const [agentActivity, setAgentActivity] = useState({})
  const [activityLoading, setActivityLoading] = useState(false)

  // Fetch agent activity on mount (and when userId changes)
  useEffect(() => {
    if (!userId) return
    setActivityLoading(true)
    fetch(`${BACKEND}/api/business/agents/activity?user_id=${encodeURIComponent(userId)}`)
      .then(r => r.json())
      .then(data => {
        const activity = data.agents || {}
        setAgentActivity(activity)
        // Update node statuses from activity data
        setNodes(prev => prev.map(n => {
          if (n.id === 'jarvis-center') return n
          const a = activity[n.id]
          if (!a) return n
          return {
            ...n,
            data: {
              ...n.data,
              agent: { ...n.data.agent, status: a.status || 'idle' },
            },
          }
        }))
      })
      .catch(() => {})
      .finally(() => setActivityLoading(false))
  }, [userId]) // eslint-disable-line react-hooks/exhaustive-deps

  const onNodeClick = useCallback((_, node) => {
    if (node.id === 'jarvis-center') return
    setSelectedAgent(node.data.agent)
  }, [])

  return (
    <div style={{ width: '100%', height: 'calc(100vh - 56px)', background: '#0a0908', position: 'relative' }}>
      <style>{`
        /* Override React Flow controls to match brand */
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

      {/* Empty state overlay */}
      <div style={{
        position: 'absolute', bottom: 40, left: '50%',
        transform: 'translateX(-50%)',
        pointerEvents: 'none', textAlign: 'center',
        fontFamily: 'var(--font-sans), system-ui, sans-serif',
        fontSize: 13, color: 'rgba(243,234,217,0.35)',
        maxWidth: 420, lineHeight: 1.6,
      }}>
        No active runs. Trigger an Operator cycle or start a Creation 1.0 task to see agents activate here.
      </div>

      <AgentInspectorPanel
        agent={selectedAgent}
        agentActivity={agentActivity[selectedAgent?.id]}
        activityLoading={activityLoading}
        onClose={() => setSelectedAgent(null)}
      />
    </div>
  )
}
