'use client'
import { motion } from 'framer-motion'
import { useEffect, useState } from 'react'

export function Orb({ size = 220 }) {
  const [mouseOffset, setMouseOffset] = useState({ x: 0, y: 0 })

  useEffect(() => {
    function handleMove(e) {
      const cx = window.innerWidth / 2
      const cy = window.innerHeight / 2
      const dx = (e.clientX - cx) / cx
      const dy = (e.clientY - cy) / cy
      setMouseOffset({ x: dx * 12, y: dy * 12 })
    }
    window.addEventListener('mousemove', handleMove)
    return () => window.removeEventListener('mousemove', handleMove)
  }, [])

  return (
    <motion.div
      style={{
        position: 'relative',
        width: size,
        height: size,
        x: mouseOffset.x,
        y: mouseOffset.y,
      }}
      transition={{ type: 'spring', damping: 20, stiffness: 100 }}
    >
      {/* Outer aura */}
      <motion.div
        style={{
          position: 'absolute',
          inset: -size * 0.35,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(200,75,49,0.28) 0%, rgba(200,75,49,0.08) 40%, transparent 70%)',
          filter: 'blur(20px)',
        }}
        animate={{ scale: [1, 1.08, 1], opacity: [0.7, 1, 0.7] }}
        transition={{ duration: 5, repeat: Infinity, ease: 'easeInOut' }}
      />

      {/* Main orb body */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          borderRadius: '50%',
          background: 'radial-gradient(circle at 38% 35%, rgba(255,210,170,0.95) 0%, rgba(220,90,55,1) 25%, rgba(140,40,20,1) 60%, rgba(60,20,10,1) 90%)',
          boxShadow: '0 0 90px rgba(200,75,49,0.5), inset 0 0 60px rgba(40,15,8,0.6)',
        }}
      />

      {/* Inner moving highlight */}
      <motion.div
        style={{
          position: 'absolute',
          top: '18%',
          left: '22%',
          width: '42%',
          height: '42%',
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(255,235,210,0.95) 0%, rgba(255,180,130,0.4) 30%, transparent 65%)',
          filter: 'blur(8px)',
        }}
        animate={{ x: [0, 6, -4, 2, 0], y: [0, -4, 5, -2, 0] }}
        transition={{ duration: 10, repeat: Infinity, ease: 'easeInOut' }}
      />

      {/* Subtle outer ring */}
      <div
        style={{
          position: 'absolute',
          inset: -8,
          borderRadius: '50%',
          border: '1px solid rgba(200,75,49,0.15)',
          pointerEvents: 'none',
        }}
      />
    </motion.div>
  )
}
