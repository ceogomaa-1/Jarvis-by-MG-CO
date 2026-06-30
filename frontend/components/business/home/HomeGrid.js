'use client'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Responsive, WidthProvider } from 'react-grid-layout'
import HomeBlock from './HomeBlock'
import CustomBlock from './CustomBlock'

const ResponsiveGridLayout = WidthProvider(Responsive)

const BREAKPOINTS = { lg: 1200, md: 996, sm: 768, xs: 0 }
const COLS = { lg: 12, md: 10, sm: 6, xs: 1 }

// react-grid-layout's required CSS, inlined so we don't depend on a global CSS import
// (and so we can respect prefers-reduced-motion). Scoped under .jarvis-home-grid.
const GRID_CSS = `
.jarvis-home-grid .react-grid-layout { position: relative; transition: height 200ms ease; }
.jarvis-home-grid .react-grid-item { transition: all 200ms ease; transition-property: left, top, width, height; }
.jarvis-home-grid .react-grid-item.cssTransforms { transition-property: transform, width, height; }
.jarvis-home-grid .react-grid-item.resizing { transition: none; z-index: 3; will-change: width, height; }
.jarvis-home-grid .react-grid-item.react-draggable-dragging { transition: none; z-index: 4; will-change: transform; }
.jarvis-home-grid .react-grid-item.react-grid-placeholder { background: rgba(45,127,249,0.16); border: 1px dashed rgba(45,127,249,0.45); border-radius: 14px; transition-duration: 100ms; z-index: 2; }
.jarvis-home-grid .react-grid-item > .react-resizable-handle { position: absolute; width: 20px; height: 20px; bottom: 0; right: 0; cursor: se-resize; }
.jarvis-home-grid .react-grid-item > .react-resizable-handle::after { content: ""; position: absolute; right: 5px; bottom: 5px; width: 6px; height: 6px; border-right: 2px solid rgba(255,255,255,0.28); border-bottom: 2px solid rgba(255,255,255,0.28); }
@media (prefers-reduced-motion: reduce) {
  .jarvis-home-grid .react-grid-layout,
  .jarvis-home-grid .react-grid-item,
  .jarvis-home-grid .react-grid-item.cssTransforms { transition: none !important; }
}
`

export default function HomeGrid({ layout, blocks, onAction, onHideBlock, onLayoutChange, userId, onCustomChanged, onCustomDelete }) {
  const [mounted, setMounted] = useState(false)
  const latestLayouts = useRef(layout?.layouts || {})
  useEffect(() => { setMounted(true) }, [])

  const blockMap = useMemo(() => {
    const m = {}
    for (const b of blocks || []) m[b.block_key] = b
    return m
  }, [blocks])

  const hidden = new Set(layout?.hidden || [])
  const visibleKeys = (layout?.order || []).filter(k => !hidden.has(k))

  if (!mounted) {
    return <div style={{ minHeight: 320 }} />  // avoid WidthProvider hydration mismatch
  }

  return (
    <div className="jarvis-home-grid" style={{ width: '100%' }}>
      <style>{GRID_CSS}</style>
      <ResponsiveGridLayout
        layouts={layout?.layouts || {}}
        breakpoints={BREAKPOINTS}
        cols={COLS}
        rowHeight={86}
        margin={[14, 14]}
        containerPadding={[2, 2]}
        draggableHandle=".home-drag-handle"
        compactType="vertical"
        preventCollision={false}
        isResizable
        isDraggable
        onLayoutChange={(_current, all) => { latestLayouts.current = all }}
        onDragStop={() => onLayoutChange?.(latestLayouts.current)}
        onResizeStop={() => onLayoutChange?.(latestLayouts.current)}
      >
        {visibleKeys.map((key) => {
          const block = blockMap[key]
          return (
            <div key={key} style={{ overflow: 'hidden' }}>
              {block && block.custom ? (
                <CustomBlock block={block} userId={userId} onChanged={onCustomChanged} onDelete={onCustomDelete} />
              ) : block ? (
                <HomeBlock block={block} onAction={onAction} onRemove={onHideBlock} />
              ) : (
                <div className="os1-card" style={{
                  height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  borderRadius: 14, border: '1px dashed var(--os1-border-soft, rgba(255,255,255,0.08))',
                  color: 'var(--os1-text-faint, #6E6E6C)',
                }}>
                  <span className="font-pixel" style={{ fontSize: 10 }}>Jarvis is composing this…</span>
                </div>
              )}
            </div>
          )
        })}
      </ResponsiveGridLayout>
    </div>
  )
}
