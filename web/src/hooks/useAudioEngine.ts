import { AudioEngine } from "../audio";

/**
 * Lazily construct a single {@link AudioEngine} for the app's lifetime.
 *
 * The engine wraps Tone's *global* transport + AudioContext and registers
 * transport listeners in its constructor, so it must exist exactly once — the
 * module-level singleton guarantees that however many components need it
 * (App, the Guitar Arranger Lab, …) share one engine. (We deliberately don't
 * wrap the app in <StrictMode>, whose simulated double-mount would otherwise
 * create two engines competing over the one global transport.)
 */
let engine: AudioEngine | null = null;

export function useAudioEngine(): AudioEngine {
  return (engine ??= new AudioEngine());
}
