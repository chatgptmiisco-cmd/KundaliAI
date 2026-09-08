import { Insight, InsightTone, KundaliSummary, Language, PreferenceKey } from '../types/kundali';

interface Copy {
  title: string;
  message: string;
  tone: InsightTone;
}

function buildCopy(
  pref: PreferenceKey,
  language: Language,
  summary: KundaliSummary,
): Copy {
  const isManglik = summary.manglik.isManglik;

  const table: Record<PreferenceKey, Record<Language, Copy>> = {
    marriageRelationships: {
      en: {
        title: 'Marriage & Relationships',
        tone: isManglik ? 'watch' : 'good',
        message: isManglik
          ? 'Your Manglik placement is worth factoring into chart matching — nothing to worry about, just something to discuss openly.'
          : 'Your chart shows steady, supportive placements for partnership right now.',
      },
      hi: {
        title: 'विवाह और रिश्ते',
        tone: isManglik ? 'watch' : 'good',
        message: isManglik
          ? 'आपकी मंगलिक स्थिति को कुंडली मिलान में ध्यान में रखना अच्छा रहेगा — चिंता की बात नहीं, बस खुलकर चर्चा करने लायक विषय है।'
          : 'फिलहाल आपकी कुंडली में साझेदारी के लिए स्थिर और सहायक स्थिति है।',
      },
    },
    career: {
      en: { title: 'Career', tone: 'good', message: `Your core strength — ${summary.coreStrength} — is working in your favour at work right now.` },
      hi: { title: 'करियर', tone: 'good', message: `आपकी मुख्य शक्ति — ${summary.coreStrength} — फिलहाल काम में आपके पक्ष में है।` },
    },
    health: {
      en: {
        title: 'Health',
        tone: 'average',
        message: `Keep an eye on ${summary.coreChallenge.toLowerCase()} — a steady routine helps more than a strict one right now.`,
      },
      hi: {
        title: 'स्वास्थ्य',
        tone: 'average',
        message: `${summary.coreChallenge} पर ध्यान दें — फिलहाल सख्त नहीं, नियमित दिनचर्या ज़्यादा मदद करेगी।`,
      },
    },
    family: {
      en: { title: 'Family', tone: 'good', message: 'Family matters look steady — a good time to have overdue conversations calmly.' },
      hi: { title: 'परिवार', tone: 'good', message: 'पारिवारिक मामले स्थिर दिख रहे हैं — टली हुई बातचीत शांति से करने का अच्छा समय है।' },
    },
    friends: {
      en: {
        title: 'Friends',
        tone: 'good',
        message: 'A good stretch for friendships and group plans — reach out to someone you have been meaning to.',
      },
      hi: {
        title: 'दोस्ती',
        tone: 'good',
        message: 'दोस्ती और समूह की योजनाओं के लिए अच्छा समय है — जिससे बात करना टाल रहे थे, उससे संपर्क करें।',
      },
    },
  };

  return table[pref][language];
}

export function buildInsights(
  preferences: PreferenceKey[],
  language: Language,
  summary: KundaliSummary,
): Insight[] {
  return preferences.map((pref) => {
    const copy = buildCopy(pref, language, summary);
    return {
      id: pref,
      preference: pref,
      tone: copy.tone,
      title: copy.title,
      message: copy.message,
    };
  });
}
