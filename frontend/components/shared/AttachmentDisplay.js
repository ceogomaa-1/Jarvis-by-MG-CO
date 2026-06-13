'use client'
import { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { FileText, FileSpreadsheet, X } from 'lucide-react'
import { getAttachmentSignedUrl, isImageAttachment, formatFileSize, truncateMiddle } from '../../lib/attachments'

function iconForAttachment(att) {
  const name = (att?.name || '').toLowerCase()
  const mt = att?.media_type || att?.type || ''
  if (mt === 'text/csv' || name.endsWith('.csv')) return FileSpreadsheet
  return FileText
}

function Lightbox({ url, onClose }) {
  if (typeof document === 'undefined') return null
  return createPortal(
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000, cursor: 'zoom-out',
      }}
    >
      <button
        onClick={onClose}
        style={{
          position: 'absolute', top: 20, right: 20, width: 36, height: 36, borderRadius: 999,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.1)',
          color: 'var(--ink-soft)', cursor: 'pointer',
        }}
      >
        <X size={20} />
      </button>
      <motion.img
        initial={{ scale: 0.96 }} animate={{ scale: 1 }}
        src={url} alt=""
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: '90vw', maxHeight: '88vh', borderRadius: 12, border: '1px solid rgba(255,255,255,0.1)', cursor: 'default' }}
      />
    </motion.div>,
    document.body
  )
}

function ImageThumb({ att }) {
  const [url, setUrl] = useState(att.preview_url || null)
  const [error, setError] = useState(false)
  const [lightboxOpen, setLightboxOpen] = useState(false)

  useEffect(() => {
    if (url || !att.storage_path) return
    let cancelled = false
    getAttachmentSignedUrl(att.storage_path).then(signed => {
      if (cancelled) return
      if (signed) setUrl(signed)
      else setError(true)
    })
    return () => { cancelled = true }
  }, [url, att.storage_path])

  if (error) {
    return (
      <div style={{
        width: 120, height: 120, borderRadius: 12,
        background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', padding: 8,
      }}>
        <span style={{ fontSize: 10, fontFamily: 'system-ui, sans-serif', color: 'rgba(243,234,217,0.4)' }}>expired — re-upload</span>
      </div>
    )
  }

  if (!url) {
    return <div className="onboarding-pulse" style={{ width: 120, height: 120, borderRadius: 12, border: '1px solid rgba(255,255,255,0.1)', background: 'rgba(255,255,255,0.03)' }} />
  }

  return (
    <>
      <img
        src={url} alt=""
        onClick={() => setLightboxOpen(true)}
        style={{ width: 120, height: 120, objectFit: 'cover', borderRadius: 12, border: '1px solid rgba(255,255,255,0.1)', cursor: 'zoom-in' }}
      />
      <AnimatePresence>
        {lightboxOpen && <Lightbox url={url} onClose={() => setLightboxOpen(false)} />}
      </AnimatePresence>
    </>
  )
}

function FileChip({ att }) {
  const [state, setState] = useState('idle') // idle | loading | error
  const Icon = iconForAttachment(att)

  async function handleClick() {
    if (state === 'loading') return
    if (att.preview_url) {
      window.open(att.preview_url, '_blank', 'noopener')
      return
    }
    if (!att.storage_path) return
    setState('loading')
    const url = await getAttachmentSignedUrl(att.storage_path)
    if (url) {
      window.open(url, '_blank', 'noopener')
      setState('idle')
    } else {
      setState('error')
    }
  }

  return (
    <div
      onClick={handleClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 10, maxWidth: 240,
        background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
        borderRadius: 12, padding: '10px 14px', cursor: 'pointer',
      }}
    >
      <Icon size={16} color="rgba(243,234,217,0.55)" style={{ flexShrink: 0 }} />
      <div style={{ minWidth: 0, flex: 1, textAlign: 'left' }}>
        <div style={{
          fontSize: 13, fontFamily: 'system-ui, sans-serif', color: 'rgba(243,234,217,0.9)',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>
          {truncateMiddle(att.name, 26)}
        </div>
        <div className={state === 'loading' ? 'onboarding-pulse' : ''} style={{ fontSize: 11, fontFamily: 'system-ui, sans-serif', color: 'rgba(243,234,217,0.4)' }}>
          {state === 'error' ? 'expired — re-upload' : state === 'loading' ? 'opening…' : formatFileSize(att.size)}
        </div>
      </div>
    </div>
  )
}

export function AttachmentsRow({ attachments }) {
  if (!attachments || attachments.length === 0) return null
  const images = attachments.filter(isImageAttachment)
  const files = attachments.filter(a => !isImageAttachment(a))
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end', marginBottom: 6 }}>
      {files.map((att, i) => <FileChip key={`f-${att.storage_path || att.name || i}`} att={att} />)}
      {images.map((att, i) => <ImageThumb key={`i-${att.storage_path || att.name || i}`} att={att} />)}
    </div>
  )
}
