'use client'
import { useEffect, useRef } from 'react'
import { createRoot } from 'react-dom/client'

export default function AgentationProvider() {
  const mountRef = useRef(null)

  useEffect(() => {
    if (process.env.NODE_ENV !== 'development') return
    // Dynamic import — webpack will NOT bundle this in production builds
    // because it only runs inside useEffect (client-side, runtime only)
    const pkgName = ['agentation'].join('')
    import(/* webpackIgnore: true */ pkgName)
      .then(({ Agentation }) => {
        if (!mountRef.current) return
        const root = createRoot(mountRef.current)
        root.render(
          <Agentation
            endpoint="http://localhost:4747"
            onSessionCreated={(id) => console.log('Agentation session:', id)}
          />
        )
      })
      .catch(() => {})
  }, [])

  return <div ref={mountRef} />
}
