const fs = require('fs')
const path = require('path')

const publicDir = path.join(__dirname, '..', 'public')
const vadDir = path.join(__dirname, '..', 'node_modules', '@ricky0123', 'vad-web', 'dist')
const ortDir = path.join(__dirname, '..', 'node_modules', 'onnxruntime-web', 'dist')

const files = [
  { from: vadDir, name: 'silero_vad_legacy.onnx' },
  { from: vadDir, name: 'vad.worklet.bundle.min.js' },
  { from: ortDir, name: 'ort-wasm-simd-threaded.wasm' },
  { from: ortDir, name: 'ort-wasm-simd-threaded.jsep.wasm' },
]

let copied = 0
for (const f of files) {
  const src = path.join(f.from, f.name)
  const dest = path.join(publicDir, f.name)
  if (fs.existsSync(src)) {
    fs.copyFileSync(src, dest)
    console.log(`✓ Copied ${f.name}`)
    copied++
  } else {
    console.warn(`⚠ Missing ${src} — skipping`)
  }
}
console.log(`VAD assets: ${copied}/${files.length} copied to public/`)
