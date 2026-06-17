'use client'

import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { updateStudyNote, deleteStudyNote } from '../../lib/studyApi'
import { uploadChatAttachment, getAttachmentSignedUrl } from '../../lib/attachments'

const CREAM = '#F3EAD9'
const ACCENT = 'var(--accent, #ff9072)'

const fileToDataUrl = (file) => new Promise((resolve, reject) => {
  const r = new FileReader(); r.onload = () => resolve(r.result); r.onerror = reject; r.readAsDataURL(file)
})

// Full-screen note — Apple Notes style: open, read, edit (text + images), close.
export default function StudyNoteView({ note, userId, onClose, onSaved, onDeleted }) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(note.content || '')
  const [cat, setCat] = useState(note.category || 'General')
  const [images, setImages] = useState(note.images || []) // [{path,name}] or {dataUrl} for unsaved
  const [urls, setUrls] = useState({})                     // path -> signed url
  const [saving, setSaving] = useState(false)
  const fileRef = useRef(null)

  // Resolve signed URLs for stored images
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const next = {}
      for (const img of images) {
        if (img.path && !urls[img.path]) {
          const u = await getAttachmentSignedUrl(img.path).catch(() => null)
          if (u) next[img.path] = u
        }
      }
      if (!cancelled && Object.keys(next).length) setUrls(prev => ({ ...prev, ...next }))
    })()
    return () => { cancelled = true }
  }, [images]) // eslint-disable-line react-hooks/exhaustive-deps

  const addPhotos = async (e) => {
    const files = Array.from(e.target.files || [])
    e.target.value = ''
    for (const f of files) {
      if (!f.type?.startsWith('image/')) continue
      const dataUrl = await fileToDataUrl(f).catch(() => null)
      if (dataUrl) setImages(prev => [...prev, { dataUrl, _file: f, name: f.name }])
    }
  }

  const removeImage = (idx) => setImages(prev => prev.filter((_, i) => i !== idx))

  const save = async () => {
    setSaving(true)
    try {
      // Upload any new (unsaved) images first
      const resolved = []
      for (const img of images) {
        if (img.path) { resolved.push({ path: img.path, name: img.name || 'image' }); continue }
        if (img._file) {
          const path = await uploadChatAttachment(img._file, userId).catch(() => null)
          if (path) resolved.push({ path, name: img.name || 'image' })
        }
      }
      const updated = await updateStudyNote(userId, note.id, { content: text.trim(), category: cat.trim() || 'General', images: resolved })
      setImages(resolved)
      setEditing(false)
      onSaved?.(updated)
    } catch (err) {
      console.error('[StudyNoteView] save failed', err)
    } finally {
      setSaving(false)
    }
  }

  const remove = async () => {
    try { await deleteStudyNote(userId, note.id) } catch (e) { console.error(e) }
    onDeleted?.(note.id)
    onClose?.()
  }

  const imgSrc = (img) => img.dataUrl || urls[img.path] || null

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 60, background: '#1A1A1A', display: 'flex', flexDirection: 'column', animation: 'fadeUp 220ms ease both' }}>
      {/* Top bar */}
      <div style={{ height: 56, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 12px', borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
        <button onClick={onClose} style={{ display: 'flex', alignItems: 'center', gap: 4, background: 'none', border: 0, color: ACCENT, cursor: 'pointer', fontFamily: 'var(--sans)', fontSize: 15, padding: 8 }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
          Notes
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          {!editing && (
            <button onClick={remove} aria-label="delete" style={{ background: 'none', border: 0, color: 'rgba(243,234,217,0.55)', cursor: 'pointer', padding: 8 }}
              onMouseEnter={e => e.currentTarget.style.color = '#fca5a5'} onMouseLeave={e => e.currentTarget.style.color = 'rgba(243,234,217,0.55)'}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /></svg>
            </button>
          )}
          {editing ? (
            <button onClick={save} disabled={saving} style={{ background: ACCENT, border: 0, borderRadius: 999, color: '#1a0e08', cursor: 'pointer', fontFamily: 'var(--sans)', fontSize: 14, fontWeight: 600, padding: '7px 18px' }}>
              {saving ? 'Saving…' : 'Done'}
            </button>
          ) : (
            <button onClick={() => setEditing(true)} style={{ background: 'none', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 999, color: CREAM, cursor: 'pointer', fontFamily: 'var(--sans)', fontSize: 14, padding: '7px 16px' }}>
              Edit
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '16px 18px 40px' }}>
        <div style={{ maxWidth: 720, margin: '0 auto' }}>
          {/* Subject */}
          {editing ? (
            <input value={cat} onChange={e => setCat(e.target.value)} placeholder="Subject"
              style={{ display: 'inline-block', marginBottom: 14, background: 'rgba(255,144,114,0.1)', border: '1px solid rgba(255,144,114,0.3)', borderRadius: 999, padding: '5px 14px', color: ACCENT, fontFamily: 'var(--sans)', fontSize: 12, letterSpacing: '0.06em', textTransform: 'uppercase', outline: 'none' }} />
          ) : (
            <div style={{ display: 'inline-block', marginBottom: 14, background: 'rgba(255,144,114,0.1)', border: '1px solid rgba(255,144,114,0.3)', borderRadius: 999, padding: '5px 14px', color: ACCENT, fontFamily: 'var(--sans)', fontSize: 12, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
              {cat}
            </div>
          )}

          {/* Content */}
          {editing ? (
            <textarea value={text} onChange={e => setText(e.target.value)} placeholder="Your note…"
              style={{ width: '100%', boxSizing: 'border-box', minHeight: 240, resize: 'vertical', background: 'transparent', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 12, padding: '14px', color: CREAM, fontFamily: 'var(--sans)', fontSize: 15.5, lineHeight: 1.6, outline: 'none' }} />
          ) : (
            <div className="study-prose" style={{ color: CREAM, fontFamily: 'var(--sans)', fontSize: 16, lineHeight: 1.65 }}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{text || '_(empty note)_'}</ReactMarkdown>
            </div>
          )}

          {/* Images */}
          {(images.length > 0 || editing) && (
            <div style={{ marginTop: 20 }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: 10 }}>
                {images.map((img, i) => {
                  const src = imgSrc(img)
                  return (
                    <div key={img.path || i} style={{ position: 'relative', aspectRatio: '3/4', borderRadius: 10, overflow: 'hidden', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }}>
                      {src
                        ? <img src={src} alt={img.name || ''} style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
                        : <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'rgba(243,234,217,0.4)', fontSize: 11 }}>loading…</div>}
                      {editing && (
                        <button onClick={() => removeImage(i)} aria-label="remove image"
                          style={{ position: 'absolute', top: 6, right: 6, width: 22, height: 22, borderRadius: '50%', background: 'rgba(0,0,0,0.7)', border: '1px solid rgba(255,255,255,0.3)', color: '#fff', cursor: 'pointer', fontSize: 14, lineHeight: 1, padding: 0 }}>×</button>
                      )}
                    </div>
                  )
                })}
                {editing && (
                  <button onClick={() => fileRef.current?.click()}
                    style={{ aspectRatio: '3/4', borderRadius: 10, cursor: 'pointer', background: 'rgba(255,255,255,0.04)', border: '1px dashed rgba(255,255,255,0.2)', color: 'rgba(243,234,217,0.6)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 6, fontFamily: 'var(--sans)', fontSize: 12 }}>
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
                    Add photo
                  </button>
                )}
              </div>
              <input ref={fileRef} type="file" accept="image/*" multiple style={{ display: 'none' }} onChange={addPhotos} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
