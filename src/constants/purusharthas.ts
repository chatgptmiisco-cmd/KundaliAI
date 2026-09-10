export type PurusharthaKey = 'dharma' | 'artha' | 'kama' | 'moksha';

/** Which houses fall under each of the four classical life-aims — the
 * grouping Layer 2 of the Charts redesign organizes the house-by-house
 * breakdown into, instead of a flat 1-12 list. */
export const PURUSHARTHA_HOUSES: Record<PurusharthaKey, number[]> = {
  dharma: [1, 5, 9],
  artha: [2, 6, 10],
  kama: [3, 7, 11],
  moksha: [4, 8, 12],
};

export const PURUSHARTHA_ORDER: PurusharthaKey[] = ['dharma', 'artha', 'kama', 'moksha'];
