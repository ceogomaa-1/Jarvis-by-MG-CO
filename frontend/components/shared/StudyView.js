'use client'

// ─────────────────────────────────────────────────────────────────────────────
// Study Mode — Jarvis Personal
//
// UI-ONLY batch. This builds the look exactly (the view + the toggle pill).
// The 4 quick actions, photo-capture, note organization, and the tutor brain
// are the next batch — buttons here are placeholders (console.log only).
// ─────────────────────────────────────────────────────────────────────────────

const CREAM = '#F3EAD9'

// ─── Toggle pill ──────────────────────────────────────────────────────────────
// Stays in the SAME top-right position in both views. Only its label + switch
// state change. `studyMode=false` → reads "Study Mode" (OFF look); tapping turns
// study ON. `studyMode=true` → reads "Normal Chat" (ON look); tapping turns it OFF.
export function StudyToggle({ studyMode, onToggle }) {
  const label = studyMode ? 'Normal Chat' : 'Study Mode'
  const on = studyMode
  return (
    <button
      onClick={onToggle}
      aria-label={studyMode ? 'Switch to Normal Chat' : 'Switch to Study Mode'}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 9,
        padding: '6px 10px 6px 14px',
        background: '#2A2A2A',
        border: '1px solid rgba(255,255,255,0.12)',
        borderRadius: 999,
        cursor: 'pointer',
        userSelect: 'none',
        whiteSpace: 'nowrap',
      }}
    >
      <span style={{
        fontFamily: 'var(--sans)', fontSize: 12.5, color: CREAM,
        letterSpacing: '0.01em', fontWeight: 400,
      }}>
        {label}
      </span>
      {/* iOS-style switch */}
      <span style={{
        position: 'relative', width: 34, height: 20, borderRadius: 999,
        background: on ? 'var(--accent, #ff9072)' : 'rgba(255,255,255,0.18)',
        transition: 'background 220ms ease', flexShrink: 0,
      }}>
        <span style={{
          position: 'absolute', top: 2, left: on ? 16 : 2,
          width: 16, height: 16, borderRadius: '50%',
          background: '#fff',
          transition: 'left 220ms cubic-bezier(0.4,0,0.2,1)',
          boxShadow: '0 1px 3px rgba(0,0,0,0.35)',
        }} />
      </span>
    </button>
  )
}

// ─── Quick action button ──────────────────────────────────────────────────────
function ActionButton({ label }) {
  return (
    <button
      onClick={() => console.log(`[StudyMode] action: ${label}`)}
      style={{
        width: 150, height: 58,
        background: 'rgba(255,255,255,0.06)',
        border: '1px solid rgba(255,255,255,0.05)',
        borderRadius: 18,
        color: CREAM,
        fontFamily: 'var(--sans)', fontSize: 15, fontWeight: 500,
        letterSpacing: '0.01em',
        cursor: 'pointer',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        transition: 'background 180ms ease',
      }}
      onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.10)' }}
      onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.06)' }}
    >
      {label}
    </button>
  )
}

// ─── Light input bar (intentionally light, unlike normal chat's dark bar) ──────
function StudyInputBar() {
  const iconColor = '#5A5A5A'
  return (
    <div style={{
      width: '100%', maxWidth: 393, margin: '0 auto',
      display: 'flex', alignItems: 'center', gap: 14,
      padding: '12px 14px',
      background: '#ECECEC',
      borderRadius: 20,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexShrink: 0, color: iconColor }}>
        {/* image / photo */}
        <button aria-label="add image" style={iconBtn}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <rect x="3" y="3" width="18" height="18" rx="3" />
            <circle cx="8.5" cy="8.5" r="1.6" />
            <path d="M21 15l-5-5L5 21" />
          </svg>
        </button>
        {/* code */}
        <button aria-label="code" style={iconBtn}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M8 6l-5 6 5 6M16 6l5 6-5 6" />
          </svg>
        </button>
        {/* mic */}
        <button aria-label="voice" style={iconBtn}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <rect x="9" y="3" width="6" height="12" rx="3" />
            <path d="M5 11a7 7 0 0 0 14 0" />
            <line x1="12" y1="18" x2="12" y2="22" />
          </svg>
        </button>
      </div>
      <input
        placeholder="Ask Jarvis"
        style={{
          flex: 1, minWidth: 0, background: 'transparent', border: 0, outline: 'none',
          color: '#1A1A1A', fontFamily: 'var(--sans)', fontSize: 16, fontWeight: 400,
        }}
      />
      {/* dark circular send */}
      <button
        aria-label="send"
        onClick={() => console.log('[StudyMode] send')}
        style={{
          width: 36, height: 36, borderRadius: '50%', flexShrink: 0,
          background: '#1A1A1A', border: 0, cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 19V5M6 11l6-6 6 6" />
        </svg>
      </button>
    </div>
  )
}

const iconBtn = {
  background: 'none', border: 0, padding: 0, cursor: 'pointer',
  display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'inherit',
}

// ─── Greeting helper ──────────────────────────────────────────────────────────
function timeOfDay() {
  const h = new Date().getHours()
  if (h < 12) return 'Good Morning'
  if (h < 18) return 'Good Afternoon'
  return 'Good Evening'
}

// ─── Study view ───────────────────────────────────────────────────────────────
export default function StudyView({ name, onToggle, onMenu }) {
  const displayName = name || 'there'
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 5,
      background: '#1A1A1A',
      display: 'flex', flexDirection: 'column',
      animation: 'fadeUp 300ms ease both',
    }}>
      {/* Header */}
      <div style={{
        height: 56, flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 18px',
      }}>
        <button
          onClick={onMenu}
          aria-label="menu"
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 6, display: 'flex', flexDirection: 'column', gap: 5, alignItems: 'center' }}
        >
          <span style={{ display: 'block', width: 22, height: 2, background: CREAM, borderRadius: 1 }} />
          <span style={{ display: 'block', width: 22, height: 2, background: CREAM, borderRadius: 1 }} />
          <span style={{ display: 'block', width: 22, height: 2, background: CREAM, borderRadius: 1 }} />
        </button>
        <StudyToggle studyMode={true} onToggle={onToggle} />
      </div>

      {/* Centered content */}
      <div style={{
        flex: 1, minHeight: 0,
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        paddingTop: 32,
      }}>
        {/* Orb / mono planet logo */}
        <img
          src="/jarvis-logo-mono.png"
          alt=""
          style={{ width: 77, height: 77, objectFit: 'contain', userSelect: 'none' }}
          draggable={false}
        />

        {/* Greeting */}
        <div style={{
          marginTop: 22,
          fontFamily: 'var(--font-display-round), var(--sans)',
          fontSize: 24, fontWeight: 600, color: CREAM,
          textAlign: 'center', letterSpacing: '0.01em',
        }}>
          {timeOfDay()}, {displayName}
        </div>

        {/* 2×2 quick actions */}
        <div style={{
          marginTop: 56,
          display: 'grid', gridTemplateColumns: 'repeat(2, 150px)', gap: 16,
        }}>
          <ActionButton label="Capture a note" />
          <ActionButton label="Quick Quiz" />
          <ActionButton label="Summarize" />
          <ActionButton label="Research" />
        </div>
      </div>

      {/* Light input bar pinned to bottom */}
      <div style={{ flexShrink: 0, padding: '0 16px 20px' }}>
        <StudyInputBar />
      </div>
    </div>
  )
}
