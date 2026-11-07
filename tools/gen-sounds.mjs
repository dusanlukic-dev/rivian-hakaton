#!/usr/bin/env node
// Generates the alert sounds used by the phone app (Android res/raw via expo-notifications)
// and the web dashboard. Pure Node, no dependencies. Re-run after tweaking: `node tools/gen-sounds.mjs`
//
// Names must be valid Android resource names: lowercase letters, digits, underscore.
//   chime.wav           level 1 "notice"   – soft two-tone ding (car screen)
//   alarm_warning.wav   level 2 "warning"  – 3 high beeps, 1 s loop (car screen)
//   alarm_critical.wav  red zone ("critical") – calm bell, three rising notes, then a rest (1.6 s). Phone only.
//   alarm_siren.wav     emergency – fast, bright bell bursts, 1 s loop. Phone (in-app loop + the emergency
//                       notification channel) and the car screen.
// The phone plays only the last two (D53). The car screen's warning beeps sit at 2–4 kHz (where hearing is most
// sensitive); the phone's bells are sine-based with soft attacks on purpose: drivers found the old square-wave
// siren painful. The emergency is the stronger one through rhythm, brightness and loudness, not a harsh timbre.

import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUT_DIRS = [
  join(ROOT, 'frontend/mobile/assets/sounds'),
  join(ROOT, 'frontend/dashboard/public/sounds'),
];
const RATE = 44100;

/** Tone with short linear attack/release so beeps don't click. */
function tone(buf, startS, durS, freqs, amp, { attack = 0.005, release = 0.01, decay = 0 } = {}) {
  const start = Math.round(startS * RATE);
  const len = Math.round(durS * RATE);
  for (let i = 0; i < len && start + i < buf.length; i++) {
    const t = i / RATE;
    let env = Math.min(1, t / attack, (durS - t) / release);
    if (decay > 0) env *= Math.exp(-t / decay);
    let s = 0;
    for (const [f, a] of freqs) s += a * Math.sin(2 * Math.PI * f * t);
    buf[start + i] += amp * Math.max(0, env) * s;
  }
}

function render(durS, draw) {
  const buf = new Float32Array(Math.round(durS * RATE));
  draw(buf);
  return buf;
}

function toWav(samples) {
  const data = Buffer.alloc(samples.length * 2);
  for (let i = 0; i < samples.length; i++) {
    const v = Math.max(-1, Math.min(1, samples[i]));
    data.writeInt16LE(Math.round(v * 32767), i * 2);
  }
  const h = Buffer.alloc(44);
  h.write('RIFF', 0); h.writeUInt32LE(36 + data.length, 4); h.write('WAVE', 8);
  h.write('fmt ', 12); h.writeUInt32LE(16, 16); h.writeUInt16LE(1, 20); h.writeUInt16LE(1, 22);
  h.writeUInt32LE(RATE, 24); h.writeUInt32LE(RATE * 2, 28); h.writeUInt16LE(2, 32); h.writeUInt16LE(16, 34);
  h.write('data', 36); h.writeUInt32LE(data.length, 40);
  return Buffer.concat([h, data]);
}

/** Scales to a peak of `peak` (overlapping notes would otherwise clip). */
function normalize(buf, peak) {
  let max = 0;
  for (const v of buf) max = Math.max(max, Math.abs(v));
  if (max > 0) for (let i = 0; i < buf.length; i++) buf[i] *= peak / max;
  return buf;
}

/** Soft clipping (tanh): louder on average without a hard buzz. */
function saturate(buf, drive) {
  for (let i = 0; i < buf.length; i++) buf[i] = Math.tanh(drive * buf[i]);
  return buf;
}

// Slightly "square-ish" timbre (fundamental + odd harmonic) reads as an alarm, not music.
const BEEP = (f) => [[f, 1], [f * 3, 0.25]];
// Sine bell with quiet 2nd/3rd harmonics: the phone's red-zone sound.
const BELL = (f) => [[f, 1], [f * 2, 0.15], [f * 3, 0.05]];
// Brighter bell (stronger harmonics): the emergency.
const BRIGHT = (f) => [[f, 1], [f * 2, 0.35], [f * 3, 0.2], [f * 4, 0.08]];

const sounds = {
  chime: render(0.7, (b) => {
    tone(b, 0.0, 0.35, [[1046.5, 1], [2093, 0.2]], 0.55, { decay: 0.18, release: 0.05 });
    tone(b, 0.18, 0.5, [[1318.5, 1], [2637, 0.2]], 0.55, { decay: 0.22, release: 0.08 });
  }),
  alarm_warning: render(1.0, (b) => {
    for (let k = 0; k < 3; k++) tone(b, k * 0.18, 0.11, BEEP(3150), 0.7);
  }),
  // Red zone: A5 – C#6 – E6 once, soft sine bell (8 ms attack, exponential decay), then a rest. Played once per
  // message while the level is critical and something risky is happening, so it repeats every ~1.6 s.
  alarm_critical: normalize(
    render(1.6, (b) => {
      for (const [t, f] of [[0.0, 880], [0.16, 1108.73], [0.32, 1318.51]]) {
        tone(b, t, 0.7, BELL(f), 0.5, { attack: 0.008, release: 0.12, decay: 0.22 });
      }
    }),
    0.7,
  ),
  // Emergency: two quick rising bursts per second, C6 – E6 – G6 – C7, the brighter bell, shorter decay, gently
  // saturated for loudness and peaked higher than the red-zone bell. Loops seamlessly every 1 s.
  alarm_siren: normalize(
    saturate(
      render(1.0, (b) => {
        for (const burst of [0, 0.5]) {
          [1046.5, 1318.51, 1567.98, 2093].forEach((f, k) => {
            // 0.27 s notes: the last one ends at 0.995 s, so the loop seam is silent (no click).
            tone(b, burst + k * 0.075, 0.27, BRIGHT(f), 0.6, { attack: 0.004, release: 0.06, decay: 0.12 });
          });
        }
      }),
      2.2,
    ),
    0.95,
  ),
};

for (const dir of OUT_DIRS) {
  mkdirSync(dir, { recursive: true });
  for (const [name, samples] of Object.entries(sounds)) {
    writeFileSync(join(dir, `${name}.wav`), toWav(samples));
  }
  console.log(`wrote ${Object.keys(sounds).length} sounds -> ${dir}`);
}
