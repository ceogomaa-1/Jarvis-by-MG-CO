'use client'
import { useEffect, useLayoutEffect } from 'react'

import { BACKEND } from '@/lib/backend'
const STORAGE_KEY = 'jarvis_font_pref'
const CLASS_NAME = 'os1-font-normal'

// Reads the cached preference synchronously (localStorage only — no network).
export function getStoredFontPref() {
  if (typeof window === 'undefined') return 'pixel'
  try {
    return localStorage.getItem(STORAGE_KEY) === 'normal' ? 'normal' : 'pixel'
  } catch {
    return 'pixel'
  }
}

// Toggles the `os1-font-normal` class on <html>, which flips --pixel everywhere.
export function applyFontPref(pref) {
  if (typeof document === 'undefined') return
  document.documentElement.classList.toggle(CLASS_NAME, pref === 'normal')
}

export function setFontPref(pref) {
  applyFontPref(pref)
  if (typeof window === 'undefined') return
  try { localStorage.setItem(STORAGE_KEY, pref) } catch {}
}

// Returns the font-family stack that --pixel currently resolves to, for use
// in canvas `ctx.font` strings (which can't read CSS custom properties).
export function getCanvasFontStack(fallback = "'Pixelify Sans', monospace") {
  if (typeof window === 'undefined') return fallback
  const value = getComputedStyle(document.documentElement).getPropertyValue('--pixel').trim()
  return value || fallback
}

export async function fetchFontPref(userId) {
  if (!userId) return null
  try {
    const res = await fetch(`${BACKEND}/api/user-preferences/${userId}`)
    if (!res.ok) return null
    const data = await res.json()
    return data.font_pref === 'normal' || data.font_pref === 'pixel' ? data.font_pref : null
  } catch {
    return null
  }
}

export async function saveFontPref(userId, pref) {
  if (!userId) return false
  try {
    const res = await fetch(`${BACKEND}/api/user-preferences/font-pref`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, font_pref: pref }),
    })
    return res.ok
  } catch {
    return false
  }
}

// Applies the cached preference before first paint (avoids font-flash), then
// reconciles with the server preference once the user is known so it follows
// them across devices.
export function useFontPref(userId) {
  useLayoutEffect(() => {
    applyFontPref(getStoredFontPref())
  }, [])

  useEffect(() => {
    if (!userId) return
    fetchFontPref(userId).then(pref => {
      if (pref) setFontPref(pref)
    })
  }, [userId])
}
