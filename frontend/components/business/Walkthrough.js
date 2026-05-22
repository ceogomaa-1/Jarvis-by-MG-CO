'use client'

function WalkthroughStep({ step }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <style>{`
        @keyframes bizFadeUp {
          from { opacity: 0; transform: translateY(6px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes bizDot {
          0%, 80%, 100% { opacity: 0.2; transform: scale(0.8); }
          40%            { opacity: 1;   transform: scale(1); }
        }
      `}</style>

      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, animation: 'bizFadeUp 280ms ease both' }}>
        <div style={{
          width: 26, height: 26, borderRadius: '50%', flexShrink: 0,
          background: 'rgba(200,75,49,0.12)', border: '1px solid rgba(200,75,49,0.35)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 11, fontWeight: 600, color: '#c84b31', fontFamily: 'system-ui, sans-serif',
        }}>
          {step.step_number}
        </div>
        <div style={{ flex: 1 }}>
          <p style={{ margin: 0, fontSize: 14, color: '#f3ead9', lineHeight: 1.55, fontFamily: 'system-ui, sans-serif' }}>
            {step.instruction}
          </p>
          {step.detail && (
            <p style={{ margin: '4px 0 0', fontSize: 12, color: 'rgba(243,234,217,0.5)', lineHeight: 1.4, fontFamily: 'system-ui, sans-serif', fontStyle: 'italic' }}>
              {step.detail}
            </p>
          )}
        </div>
      </div>

      {step.image_url && (
        <div style={{
          position: 'relative', marginTop: 10, marginLeft: 38,
          borderRadius: 8, overflow: 'hidden',
          border: '1px solid rgba(243,234,217,0.1)',
          background: '#111',
        }}>
          <img
            src={step.image_url}
            alt={`Step ${step.step_number}`}
            style={{ width: '100%', display: 'block', maxHeight: 280, objectFit: 'cover' }}
            onError={e => { e.target.parentElement.style.display = 'none' }}
          />
          {step.annotation_svg && (
            <div
              style={{ position: 'absolute', inset: 0 }}
              dangerouslySetInnerHTML={{ __html: step.annotation_svg }}
            />
          )}
        </div>
      )}
    </div>
  )
}

export default function Walkthrough({ title, intro, steps, loading }) {
  return (
    <div style={{ marginTop: 4 }}>
      {title && (
        <div style={{
          fontSize: 10, letterSpacing: '0.15em', textTransform: 'uppercase',
          color: '#c84b31', marginBottom: 10, fontWeight: 600,
          fontFamily: 'system-ui, sans-serif',
        }}>
          Walkthrough
        </div>
      )}
      {intro && (
        <p style={{
          fontSize: 13, color: 'rgba(243,234,217,0.7)', marginBottom: 16,
          lineHeight: 1.6, fontFamily: 'system-ui, sans-serif',
        }}>
          {intro}
        </p>
      )}
      {steps.map((step, i) => (
        <WalkthroughStep key={step.step_number ?? i} step={step} />
      ))}
      {loading && (
        <div style={{ display: 'flex', gap: 5, padding: '10px 0 4px', alignItems: 'center' }}>
          {[0, 1, 2].map(i => (
            <div key={i} style={{
              width: 6, height: 6, borderRadius: '50%', background: '#c84b31',
              animation: `bizDot 1.2s ease-in-out ${i * 0.2}s infinite`,
            }} />
          ))}
          <span style={{ fontSize: 11, color: 'rgba(243,234,217,0.4)', marginLeft: 6, fontFamily: 'system-ui, sans-serif' }}>
            generating steps...
          </span>
        </div>
      )}
    </div>
  )
}
