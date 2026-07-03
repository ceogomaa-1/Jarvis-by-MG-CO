'use client';

// Batch 72 "Private Office" — the loader kept its name and API (size / speed /
// showLoadingText / loadingText) so every call site upgrades in place, but the
// pixel-tetris board is gone. In its place: a hairline ring with a slow copper
// arc and a tracked machine label. Calm, corporate, expensive.

const RING_SIZES = { sm: 34, md: 48, lg: 64 };
const SPIN_SPEEDS = { fast: '1.1s', normal: '1.8s' };

export default function TetrisLoader({
  size = 'sm',
  speed = 'fast',
  showLoadingText = true,
  loadingText = 'Loading...',
}) {
  const px = RING_SIZES[size] ?? 34;
  const duration = SPIN_SPEEDS[speed] ?? '1.1s';
  const label = (loadingText || '').replace(/\.{2,}$/, '');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
      <div style={{ position: 'relative', width: px, height: px }}>
        {/* Hairline track */}
        <div style={{
          position: 'absolute', inset: 0, borderRadius: '50%',
          border: '1px solid rgba(237,230,216,0.1)',
        }} />
        {/* Copper arc */}
        <div style={{
          position: 'absolute', inset: -1, borderRadius: '50%',
          border: '1px solid transparent',
          borderTopColor: 'var(--os1-accent, #cf8a5b)',
          animation: `os1ArcSpin ${duration} cubic-bezier(0.45, 0.1, 0.55, 0.9) infinite`,
        }} />
        {/* Breathing core */}
        <div style={{
          position: 'absolute', inset: '50%', width: 4, height: 4,
          marginLeft: -2, marginTop: -2, borderRadius: '50%',
          background: 'var(--os1-accent, #cf8a5b)',
          boxShadow: '0 0 12px var(--os1-glow, rgba(207,138,91,0.25))',
          animation: 'os1Breathe 2.6s ease-in-out infinite',
        }} />
      </div>
      {showLoadingText && (
        <span className="os1-shimmer-label">{label}</span>
      )}
    </div>
  );
}
