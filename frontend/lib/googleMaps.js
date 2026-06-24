// Browser-side Google Maps JavaScript API loader (singleton).
//
// Uses a PUBLIC, referrer-restricted browser key (NEXT_PUBLIC_MAPS_BROWSER_KEY) — separate
// from the server-side Places key (LEADS_MAPS_API_KEY) so the two can be locked down
// independently (this one is restricted to the Maps JavaScript API + the jarvismgco.com
// HTTP referrer). Loads the script exactly once and resolves when window.google.maps exists.

let loaderPromise = null

export function mapsBrowserKey() {
  return (process.env.NEXT_PUBLIC_MAPS_BROWSER_KEY || '').trim()
}

export function loadGoogleMaps() {
  if (typeof window === 'undefined') return Promise.reject(new Error('no window'))
  if (window.google && window.google.maps) return Promise.resolve(window.google.maps)
  if (loaderPromise) return loaderPromise

  const key = mapsBrowserKey()
  if (!key) return Promise.reject(new Error('NEXT_PUBLIC_MAPS_BROWSER_KEY is not set'))

  loaderPromise = new Promise((resolve, reject) => {
    const existing = document.getElementById('gmaps-js')
    if (existing) {
      existing.addEventListener('load', () => resolve(window.google.maps))
      existing.addEventListener('error', reject)
      return
    }
    const s = document.createElement('script')
    s.id = 'gmaps-js'
    s.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&libraries=marker&loading=async`
    s.async = true
    s.defer = true
    s.onload = () => resolve(window.google.maps)
    s.onerror = () => { loaderPromise = null; reject(new Error('Failed to load Google Maps')) }
    document.head.appendChild(s)
  })
  return loaderPromise
}
