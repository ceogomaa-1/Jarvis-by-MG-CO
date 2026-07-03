'use client';
import { useEffect, useState } from 'react';

let MeshGradientComponent = null;

export default function ChatBackground() {
  const [dimensions, setDimensions] = useState({ width: 1920, height: 1080 });
  const [mounted, setMounted] = useState(false);
  const [Component, setComponent] = useState(null);

  useEffect(() => {
    // Lazy-load to avoid SSR issues with WebGL
    import('@paper-design/shaders-react')
      .then(mod => {
        MeshGradientComponent = mod.MeshGradient;
        setComponent(() => mod.MeshGradient);
      })
      .catch(() => {
        // WebGL or import failure — silent fallback to plain background
      });

    setMounted(true);
    const update = () =>
      setDimensions({ width: window.innerWidth, height: window.innerHeight });
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);

  if (!mounted || !Component) return null;

  return (
    <div className="fixed inset-0 z-0 pointer-events-none">
      <ErrorBoundaryShader fallback={null}>
        <Component
          width={dimensions.width}
          height={dimensions.height}
          colors={[
            '#0a0a0a',
            '#1a0f0c',
            '#050506',
            '#1c0e08',
            '#0a0a0a',
            '#140b09',
          ]}
          distortion={0.4}
          swirl={0.3}
          grainMixer={0}
          grainOverlay={0}
          speed={0.15}
          offsetX={0.05}
        />
      </ErrorBoundaryShader>
      {/* Veil — shader should be FELT not SEEN */}
      <div className="absolute inset-0 bg-[#0a0a0a]/60" />
    </div>
  );
}

// Minimal error boundary for WebGL failures
import { Component as ReactComponent } from 'react';

class ErrorBoundaryShader extends ReactComponent {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError() {
    return { hasError: true };
  }
  render() {
    if (this.state.hasError) return this.props.fallback ?? null;
    return this.props.children;
  }
}
