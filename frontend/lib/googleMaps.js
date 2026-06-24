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
    // With loading=async the Map/Marker classes are NOT ready on script onload — you must
    // await google.maps.importLibrary(). Resolving on raw onload (and calling new Map())
    // throws "Map is not a constructor". So we resolve only after the library is imported.
    const ready = () => {
      const g = window.google
      if (g?.maps?.importLibrary) {
        g.maps.importLibrary('maps')
          .then(() => resolve(g.maps))
          .catch(reject)
      } else if (g?.maps?.Map) {
        resolve(g.maps)            // legacy (non-async) path
      } else {
        reject(new Error('Google Maps loaded but Map class unavailable'))
      }
    }
    const existing = document.getElementById('gmaps-js')
    if (existing) {
      existing.addEventListener('load', ready)
      existing.addEventListener('error', reject)
      return
    }
    const s = document.createElement('script')
    s.id = 'gmaps-js'
    s.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&v=weekly&loading=async`
    s.async = true
    s.defer = true
    s.onload = ready
    s.onerror = () => { loaderPromise = null; reject(new Error('Failed to load Google Maps')) }
    document.head.appendChild(s)
  })
  return loaderPromise
}
