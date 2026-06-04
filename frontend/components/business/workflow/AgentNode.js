'use client'
import { useState } from 'react'
import { motion } from 'framer-motion'
import { Handle, Position } from '@xyflow/react'
import {
  Brain, Search, Sparkles, Package, Compass,
  PenTool, Palette, Telescope, BarChart3, FileText,
} from 'lucide-react'

const ICONS = { Brain, Search, Sparkles, Package, Compass, PenTool, Palette, Telescope, BarChart3, FileText }

const STATUS_COLOR = {
  idle:   'rgba(243,234,217,0.3)',
  active: '#c84b31',
  done:   '#7fb069',
  error:  '#ef4444',
}

export default function AgentNode({ data, selected }) {
  const { agent } = data
  const Icon = ICONS[agent.icon] || Brain
  const [hovered, setHovered] = useState(false)

  return (
    <div style={{ position: 'relative' }}>
      {/* Hidden handles */}
      <Handle type="target" position={Position.Top}    style={{ opacity: 0, pointerEvents: 'none' }} />
      <Handle type="target" position={Position.Right}  style={{ opacity: 0, pointerEvents: 'none' }} />
      <Handle type="target" position={Position.Bottom} style={{ opacity: 0, pointerEvents: 'none' }} />
      <Handle type="target" position={Position.Left}   style={{ opacity: 0, pointerEvents: 'none' }} />

      <motion.div
        onHoverStart={() => setHovered(true)}
        onHoverEnd={() => setHovered(false)}
        whileHover={{ scale: 1.06 }}
        animate={agent.status === 'active' ? {
          boxShadow: [
            '0 0 0 0px rgba(200,75,49,0.5)',
            '0 0 0 14px rgba(200,75,49,0)',
          ],
        } : {}}
        transition={agent.status === 'active' ? {
          duration: 1.4,
          repeat: Infinity,
          ease: 'easeOut',
        } : { type: 'spring', stiffness: 400, damping: 28 }}
        style={{
          width: 96, height: 96, borderRadius: 999,
          background: 'rgba(15,15,18,0.55)',
          backdropFilter: 'blur(20px) saturate(180%)',
          WebkitBackdropFilter: 'blur(20px) saturate(180%)',
          border: agent.status === 'active'
            ? '1px solid rgba(200,75,49,0.6)'
            : selected || hovered
            ? '1px solid rgba(200,75,49,0.5)'
            : '1px solid rgba(243,234,217,0.12)',
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          gap: 5, cursor: 'pointer', position: 'relative',
          transition: 'border-color 200ms',
          boxShadow: selected ? '0 0 0 2px rgba(200,75,49,0.25)' : 'none',
        }}
      >
        {/* Status dot */}
        <div style={{
          position: 'absolute', top: 8, right: 8,
          width: 6, height: 6, borderRadius: '50%',
          background: STATUS_COLOR[agent.status] || STATUS_COLOR.idle,
        }} />

        <Icon size={24} color="#f3ead9" />
        <span style={{
          fontFamily: 'var(--font-arcade), monospace',
          fontSize: 7, textTransform: 'uppercase', letterSpacing: '0.08em',
          color: 'rgba(243,234,217,0.8)', textAlign: 'center',
          lineHeight: 1.2, padding: '0 6px',
        }}>
          {agent.name}
        </span>
      </motion.div>

      {/* Hover tooltip */}
      {hovered && (
        <div style={{
          position: 'absolute', bottom: '110%', left: '50%',
          transform: 'translateX(-50%)',
          width: 220, padding: '10px 12px',
          background: 'rgba(15,15,18,0.92)',
          backdropFilter: 'blur(20px) saturate(180%)',
          WebkitBackdropFilter: 'blur(20px) saturate(180%)',
          border: '1px solid rgba(243,234,217,0.12)',
          borderRadius: 10, zIndex: 100,
          pointerEvents: 'none',
          boxShadow: '0 12px 32px rgba(0,0,0,0.5)',
        }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4,
          }}>
            <span style={{
              fontFamily: 'var(--font-sans), system-ui, sans-serif',
              fontSize: 12, fontWeight: 600, color: '#f3ead9',
            }}>
              {agent.name}
            </span>
            <span style={{
              fontSize: 9, fontWeight: 700, letterSpacing: '0.1em',
              textTransform: 'uppercase',
              color: agent.group === 'operator' ? '#c84b31' : 'rgba(243,234,217,0.5)',
              background: agent.group === 'operator' ? 'rgba(200,75,49,0.1)' : 'rgba(243,234,217,0.06)',
              padding: '1px 5px', borderRadius: 3,
            }}>
              {agent.group === 'operator' ? 'Operator' : 'Creation'}
            </span>
          </div>
          <p style={{
            fontFamily: 'var(--font-sans), system-ui, sans-serif',
            fontSize: 11, color: 'rgba(243,234,217,0.6)',
            margin: 0, lineHeight: 1.5,
          }}>
            {agent.role}
          </p>
          <div style={{
            marginTop: 6, fontSize: 9, textTransform: 'uppercase',
            letterSpacing: '0.1em',
            color: STATUS_COLOR[agent.status] || STATUS_COLOR.idle,
            fontFamily: 'var(--font-sans), system-ui, sans-serif',
          }}>
            {agent.status}
          </div>
        </div>
      )}
    </div>
  )
}
