const fs = require('fs')
const path = require('path')

const publicDir = path.join(__dirname, '..', 'public')
const vadDir = path.join(__dirname, '..', 'node_modules', '@ricky0123', 'vad-web', 'dist')
const ortDir = path.join(__dirname, '..', 'node_modules', 'onnxruntime-web', 'dist')

fs.mkdirSync(publicDir, { recursive: true })

let copied = 0

// VAD model + worklet
const vadFiles = ['silero_vad_legacy.onnx', 'vad.worklet.bundle.min.js']
for (const name of vadFiles) {
  const src = path.join(vadDir, name)
  const dest = path.join(publicDir, name)
  if (fs.existsSync(src)) {
    fs.copyFileSync(src, dest)
    console.log(`✓ Copied ${name}`)
    copied++
  } else {
    console.warn(`⚠ Missing ${src} — skipping`)
  }
}

// All ort-wasm* .wasm and .mjs files (ORT needs both at runtime)
if (fs.existsSync(ortDir)) {
  for (const file of fs.readdirSync(ortDir)) {
    if (file.startsWith('ort-wasm') && (file.endsWith('.wasm') || file.endsWith('.mjs'))) {
      fs.copyFileSync(path.join(ortDir, file), path.join(publicDir, file))
      console.log(`✓ Copied ${file}`)
      copied++
    }
  }
} else {
  console.warn(`⚠ onnxruntime-web dist not found at ${ortDir}`)
}

console.log(`VAD assets: ${copied} files copied to public/`)
