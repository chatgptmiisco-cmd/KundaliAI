import { Language, Remedy } from '../types/kundali';

// Calm, traditional, non-mandatory suggestions — framed as common practice,
// not a prescription. Keep this list short; a real remedies engine belongs
// on the backend, tailored to the actual chart.
const REMEDIES: Record<Language, Remedy[]> = {
  en: [
    { id: 'hanuman', text: 'Many people choose to recite the Hanuman Chalisa on Tuesdays.' },
    { id: 'fasting', text: 'A Tuesday fast is a common traditional practice for this placement.' },
    { id: 'coral', text: 'Wearing red coral is a traditional suggestion — best done after consulting a qualified astrologer.' },
    { id: 'temple', text: 'Visiting a Hanuman or Mangal temple on Tuesdays is a common, gentle practice.' },
  ],
  hi: [
    { id: 'hanuman', text: 'कई लोग मंगलवार को हनुमान चालीसा का पाठ करना पसंद करते हैं।' },
    { id: 'fasting', text: 'इस स्थिति के लिए मंगलवार का व्रत एक सामान्य पारंपरिक अभ्यास है।' },
    { id: 'coral', text: 'लाल मूंगा धारण करना एक पारंपरिक सुझाव है — किसी योग्य ज्योतिषी से सलाह के बाद ही करें।' },
    { id: 'temple', text: 'मंगलवार को हनुमान या मंगल मंदिर जाना एक सामान्य, सरल अभ्यास है।' },
  ],
};

export function buildRemedies(language: Language): Remedy[] {
  return REMEDIES[language];
}
