/**
 * Convert Float32Array audio (16kHz, -1..1) to a WAV File for backend STT.
 * vad-web provides 16kHz mono Float32; backend Whisper expects common formats (we send WAV).
 */
export function float32ToWavFile(samples: Float32Array, sampleRate = 16000): File {
  const numChannels = 1;
  const bitsPerSample = 16;
  const bytesPerSample = bitsPerSample / 8;
  const blockAlign = numChannels * bytesPerSample;
  const byteRate = sampleRate * blockAlign;
  const dataSize = samples.length * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);
  let offset = 0;

  function writeString(str: string) {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset++, str.charCodeAt(i));
    }
  }

  // RIFF header
  writeString("RIFF");
  view.setUint32(offset, 36 + dataSize, true);
  offset += 4;
  writeString("WAVE");
  // fmt chunk
  writeString("fmt ");
  view.setUint32(offset, 16, true);
  offset += 4; // chunk size
  view.setUint16(offset, 1, true);
  offset += 2; // PCM
  view.setUint16(offset, numChannels, true);
  offset += 2;
  view.setUint32(offset, sampleRate, true);
  offset += 4;
  view.setUint32(offset, byteRate, true);
  offset += 4;
  view.setUint16(offset, blockAlign, true);
  offset += 2;
  view.setUint16(offset, bitsPerSample, true);
  offset += 2;
  // data chunk
  writeString("data");
  view.setUint32(offset, dataSize, true);
  offset += 4;

  // Float32 -1..1 -> Int16
  for (let i = 0; i < samples.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    const v = s < 0 ? s * 0x8000 : s * 0x7fff;
    view.setInt16(offset, v, true);
  }

  const blob = new Blob([buffer], { type: "audio/wav" });
  return new File([blob], `voice-${Date.now()}.wav`, { type: "audio/wav" });
}
