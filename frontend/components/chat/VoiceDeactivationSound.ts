"use client";

const AudioContextClass =
  typeof window !== "undefined"
    ? (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)
    : null;

/**
 * Plays a short descending chime when voice mode is deactivated.
 * Two tones: E5 → A4 ("done" effect).
 */
export function playVoiceDeactivationSound(): void {
  if (!AudioContextClass) return;
  try {
    const audioCtx = new AudioContextClass();

    const playTone = (
      frequency: number,
      startTime: number,
      duration: number,
      volume: number
    ) => {
      const oscillator = audioCtx.createOscillator();
      const gainNode = audioCtx.createGain();

      oscillator.connect(gainNode);
      gainNode.connect(audioCtx.destination);

      oscillator.frequency.value = frequency;
      oscillator.type = "sine";

      gainNode.gain.setValueAtTime(0, startTime);
      gainNode.gain.linearRampToValueAtTime(volume, startTime + 0.02);
      gainNode.gain.exponentialRampToValueAtTime(0.001, startTime + duration);

      oscillator.start(startTime);
      oscillator.stop(startTime + duration);
    };

    const now = audioCtx.currentTime;
    playTone(659.25, now, 0.12, 0.25); // E5
    playTone(440, now + 0.08, 0.15, 0.2); // A4

    setTimeout(() => audioCtx.close(), 400);
  } catch (err) {
    console.warn("Could not play voice deactivation sound:", err);
  }
}
