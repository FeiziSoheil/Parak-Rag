"use client";

const AudioContextClass =
  typeof window !== "undefined"
    ? (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)
    : null;

/**
 * Plays a short ascending chime when voice mode is activated.
 * Two tones: A5 → E6 ("ding-ding").
 */
export function playVoiceActivationSound(): void {
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
    playTone(880, now, 0.15, 0.3); // A5
    playTone(1318.5, now + 0.1, 0.2, 0.25); // E6

    setTimeout(() => audioCtx.close(), 500);
  } catch (err) {
    console.warn("Could not play voice activation sound:", err);
  }
}
