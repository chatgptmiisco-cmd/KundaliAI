import { AppLanguage, Language } from '../types/kundali';

// Generated astrological content only ever exists in English or Hindi.
// Hinglish readers are, by definition, comfortable with Roman script, so we
// serve them the English content rather than fabricating a third content set.
export function toContentLanguage(language: AppLanguage): Language {
  return language === 'hi' ? 'hi' : 'en';
}
