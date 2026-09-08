import { PassOption } from '../types/kundali';

// Static catalog data (not user-specific, no network round-trip needed) —
// the credit pass options used by the Pass Store / voice chat credit system.
export const PASS_OPTIONS: PassOption[] = [
  { id: 'day', durationLabel: { en: 'Day Pass', hi: 'डे पास' }, priceInr: 49, credits: 5 },
  { id: 'week', durationLabel: { en: 'Week Pass', hi: 'वीक पास' }, priceInr: 149, credits: 25 },
];
