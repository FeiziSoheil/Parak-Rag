/**
 * Copy onnxruntime-web dist files to public so WASM/.mjs load same-origin (avoids CDN fetch/CORS errors).
 * Run after npm install (postinstall) or before dev/build.
 */
const fs = require("fs");
const path = require("path");

const src = path.join(__dirname, "..", "node_modules", "onnxruntime-web", "dist");
const dest = path.join(__dirname, "..", "public", "onnxruntime-web");

if (!fs.existsSync(src)) {
  console.warn("copy-onnx-wasm: onnxruntime-web/dist not found, skip.");
  process.exit(0);
}

function copyRecursive(from, to) {
  fs.mkdirSync(to, { recursive: true });
  for (const name of fs.readdirSync(from)) {
    const fromPath = path.join(from, name);
    const toPath = path.join(to, name);
    if (fs.statSync(fromPath).isDirectory()) {
      copyRecursive(fromPath, toPath);
    } else {
      fs.copyFileSync(fromPath, toPath);
    }
  }
}

copyRecursive(src, dest);
console.log("copy-onnx-wasm: copied onnxruntime-web/dist -> public/onnxruntime-web");
