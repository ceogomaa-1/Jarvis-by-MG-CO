// Parallax starfield for The Mind canvas — adapted from the onboarding
// cinematic's STAR_LAYERS/drawStars (frontend/components/onboarding/ParticleField.js).

const STAR_LAYERS = [
  { count: 60, speed: 0.04, opacity: 0.08, parallax: 0.05 },
  { count: 40, speed: 0.09, opacity: 0.15, parallax: 0.1 },
  { count: 20, speed: 0.16, opacity: 0.25, parallax: 0.16 },
]

export function buildStars(mobile = false) {
  const layers = mobile ? STAR_LAYERS.slice(0, 1) : STAR_LAYERS
  return layers.map(l => ({
    ...l,
    dots: Array.from({ length: l.count }, () => ({ x: Math.random(), y: Math.random() })),
  }))
}

// Draws the starfield in screen space. `pan` is the current world-space pan
// offset (used for the parallax effect); `width`/`height` are CSS pixels.
export function drawStars(ctx, stars, width, height, pan) {
  for (const layer of stars) {
    ctx.fillStyle = `rgba(163,163,163,${layer.opacity})`
    const px = -pan.x * layer.parallax
    const py = -pan.y * layer.parallax
    for (const d of layer.dots) {
      d.y += layer.speed / height
      if (d.y > 1) d.y -= 1
      let x = d.x * width + px
      let y = d.y * height + py
      // wrap into view
      x = ((x % width) + width) % width
      y = ((y % height) + height) % height
      ctx.fillRect(x, y, 1, 1)
    }
  }
}
