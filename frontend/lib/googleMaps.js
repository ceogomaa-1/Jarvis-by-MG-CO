// Browser-side Google Maps JavaScript API loader (singleton).
//
// Uses a PUBLIC, referrer-restricted browser key (NEXT_PUBLIC_MAPS_BROWSER_KEY) — separate
// from the server-side Places key (LEADS_MAPS_API_KEY) so the two can be locked down
// independently (this one is restricted to the Maps JavaScript API + the jarvismgco.com
// HTTP referrer). Loads the script exactly once and resolves when window.google.maps is ready.
//
// We load with an explicit ?callback= (NOT loading=async + new Map()). The callback only
// fires once google.maps is fully initialized, so google.maps.Map / Marker are guaranteed
// available — this avoids the "Map is not a constructor" race that loading=async introduces.

let loaderPromise = null

export function mapsBrowserKey() {
  return (process.env.NEXT_PUBLIC_MAPS_BROWSER_KEY || '').trim()
}

export function loadGoogleMaps() {
  if (typeof window === 'undefined') return Promise.reject(new Error('no window'))
  if (window.google && window.google.maps && window.google.maps.Map) {
    return Promise.resolve(window.google.maps)
  }
  if (loaderPromise) return loaderPromise

  const key = mapsBrowserKey()
  if (!key) return Promise.reject(new Error('NEXT_PUBLIC_MAPS_BROWSER_KEY is not set'))

  loaderPromise = new Promise((resolve, reject) => {
    // A script may already be in flight (e.g. StrictMode double-mount) — poll for readiness.
    if (document.getElementById('gmaps-js')) {
      const started = Date.now()
      const poll = setInterval(() => {
        if (window.google?.maps?.Map) { clearInterval(poll); resolve(window.google.maps) }
        else if (Date.now() - started > 12000) { clearInterval(poll); reject(new Error('Google Maps load timeout')) }
      }, 50)
      return
    }

    const cb = '__gmapsReady_cb'
    window[cb] = () => {
      if (window.google?.maps?.Map) resolve(window.google.maps)
      else reject(new Error('Google Maps callback fired but Map unavailable'))
      try { delete window[cb] } catch { window[cb] = undefined }
    }

    const s = document.createElement('script')
    s.id = 'gmaps-js'
    s.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&v=weekly&callback=${cb}`
    s.async = true
    s.onerror = () => { loaderPromise = null; reject(new Error('Failed to load Google Maps script')) }
    document.head.appendChild(s)
  })
  return loaderPromise
}
