#!/usr/bin/env node
// Generates the alert sounds used by the phone app (Android res/raw via expo-notifications)
// and the web dashboard. Pure Node, no dependencies. Re-run after tweaking: `node tools/gen-sounds.mjs`
//
// Names must be valid Android resource names: lowercase letters, digits, underscore.
//   chime.wav           level 1 "notice"   – soft two-tone ding
//   alarm_warning.wav   level 2 "warning"  – 3 high beeps, 1 s loop
//   alarm_critical.wav  level 3 "critical" – fast high/higher beeps, 1 s loop
// 2–4 kHz is where hearing is most sensitive, so these cut through road noise.

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

// Slightly "square-ish" timbre (fundamental + odd harmonic) reads as an alarm, not music.
const BEEP = (f) => [[f, 1], [f * 3, 0.25]];

const sounds = {
  chime: render(0.7, (b) => {
    tone(b, 0.0, 0.35, [[1046.5, 1], [2093, 0.2]], 0.55, { decay: 0.18, release: 0.05 });
    tone(b, 0.18, 0.5, [[1318.5, 1], [2637, 0.2]], 0.55, { decay: 0.22, release: 0.08 });
  }),
  alarm_warning: render(1.0, (b) => {
    for (let k = 0; k < 3; k++) tone(b, k * 0.18, 0.11, BEEP(3150), 0.7);
  }),
  alarm_critical: render(1.0, (b) => {
    for (let k = 0; k < 8; k++) tone(b, k * 0.125, 0.075, BEEP(k % 2 ? 3600 : 3000), 0.75);
  }),
};

for (const dir of OUT_DIRS) {
  mkdirSync(dir, { recursive: true });
  for (const [name, samples] of Object.entries(sounds)) {
    writeFileSync(join(dir, `${name}.wav`), toWav(samples));
  }
  console.log(`wrote ${Object.keys(sounds).length} sounds -> ${dir}`);
}
