import { RishiTone } from '../types/kundali';

export type RishiId = 'vyasa' | 'vasishtha' | 'parashara' | 'gargi' | 'agastya' | 'bhrigu';

// The generalist default persona — answers every topic directly (see the
// backend's _RISHI_SPECIALTY, which deliberately excludes this id) rather
// than specializing and redirecting like the other five.
export const DEFAULT_RISHI_ID: RishiId = 'vyasa';

export interface RishiDef {
  id: RishiId;
  name: string; // proper noun, same across all languages
  initial: string;
  /** This persona's conversational flavor — currently just descriptive
   * metadata; all six route to the same real backend /chat/astro call. */
  tone: RishiTone;
  gradient: [string, string];
  shade: string;
}

// A distinct, muted colour per Rishi — same "no alarm colour" palette
// philosophy as the rest of the app. Vyasa gets a neutral stone tone
// (deliberately not one of the five saturated specialist accents) since
// it's the default, not "a flavor."
export const RISHIS: RishiDef[] = [
  { id: 'vyasa', name: 'Vyasa', initial: 'Vy', tone: 'general', gradient: ['#b9ac8f', '#6f6248'], shade: 'rgba(111,98,72,0.28)' },
  { id: 'vasishtha', name: 'Vasishtha', initial: 'V', tone: 'traditional', gradient: ['#7a9a92', '#3f6058'], shade: 'rgba(63,96,88,0.28)' },
  { id: 'parashara', name: 'Parashara', initial: 'P', tone: 'analytical', gradient: ['#d5a456', '#9b5f20'], shade: 'rgba(155,95,32,0.28)' },
  { id: 'gargi', name: 'Gargi', initial: 'G', tone: 'direct', gradient: ['#c7838c', '#8f4d62'], shade: 'rgba(143,77,98,0.28)' },
  { id: 'agastya', name: 'Agastya', initial: 'A', tone: 'spiritual', gradient: ['#7c8fbe', '#4d5685'], shade: 'rgba(77,86,133,0.28)' },
  { id: 'bhrigu', name: 'Bhrigu', initial: 'B', tone: 'practical', gradient: ['#9279bb', '#5b447d'], shade: 'rgba(91,68,125,0.28)' },
];

export function findRishi(id: string | undefined): RishiDef {
  return RISHIS.find((r) => r.id === id) ?? RISHIS[0];
}
