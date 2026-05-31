'use client'
import { Canvas, useFrame } from '@react-three/fiber'
import { useGLTF, Bounds } from '@react-three/drei'
import { Suspense, useRef } from 'react'
import { motion } from 'framer-motion'

function RotatingModel() {
  const groupRef = useRef()
  const { scene } = useGLTF('/models/jarvis-orb.glb')

  useFrame((_, delta) => {
    if (groupRef.current) {
      groupRef.current.rotation.y += delta * 0.18
    }
  })

  return (
    <group rotation={[0.41, 0, 0]}>
      <group ref={groupRef}>
        <primitive object={scene} />
      </group>
    </group>
  )
}

useGLTF.preload('/models/jarvis-orb.glb')

export function Orb({ size = 220 }) {
  return (
    <div
      style={{
        position: 'relative',
        width: size,
        height: size,
        pointerEvents: 'none',
      }}
    >
      {/* Pulsing halo behind the model */}
      <motion.div
        style={{
          position: 'absolute',
          inset: -size * 0.4,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(200,75,49,0.40) 0%, rgba(200,75,49,0.12) 40%, transparent 72%)',
          filter: 'blur(24px)',
          pointerEvents: 'none',
          zIndex: 0,
        }}
        animate={{ scale: [1, 1.12, 1], opacity: [0.65, 1, 0.65] }}
        transition={{ duration: 5, repeat: Infinity, ease: 'easeInOut' }}
      />

      {/* Inner tight glow for extra depth */}
      <motion.div
        style={{
          position: 'absolute',
          inset: -size * 0.15,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(255,140,90,0.25) 0%, transparent 60%)',
          filter: 'blur(12px)',
          pointerEvents: 'none',
          zIndex: 0,
        }}
        animate={{ opacity: [0.5, 0.9, 0.5] }}
        transition={{ duration: 3.5, repeat: Infinity, ease: 'easeInOut' }}
      />

      {/* 3D Canvas */}
      <div style={{ position: 'relative', zIndex: 1, width: '100%', height: '100%' }}>
        <Canvas
          camera={{ position: [0, 0, 3.2], fov: 45 }}
          gl={{ antialias: true, alpha: true, preserveDrawingBuffer: false }}
          dpr={[1, 2]}
          style={{ background: 'transparent' }}
        >
          {/* Three-point lighting — preserves model's true crimson + adds cool rim for atmosphere */}
          <ambientLight intensity={0.9} />
          <directionalLight position={[5, 4, 5]} intensity={3.2} color="#ffffff" />
          <directionalLight position={[-4, -1, -3]} intensity={2.2} color="#5878ff" />
          <directionalLight position={[0, -3, 4]} intensity={0.7} color="#ffd0c0" />
          <Suspense fallback={null}>
            <Bounds fit clip margin={0.95}>
              <RotatingModel />
            </Bounds>
          </Suspense>
        </Canvas>
      </div>
    </div>
  )
}
