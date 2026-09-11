import { Language, RishiTone } from '../types/kundali';

// Canned reply pools per persona tone, used ONLY when the real backend chat
// (which answers from the user's actual computed chart — see
// app.services.interpretation.templates.chat_reply) is unreachable, or for a
// user without Strategy-tier access. These must NEVER state a specific chart
// fact (a placement, a house, a dasha lord) since this pool has no idea what
// the user's real chart actually contains — doing so previously meant every
// user saw the same fabricated "Your Moon is in Cancer" style claims
// regardless of their real birth data. Kept tone-appropriate per persona,
// but honest about being a fallback rather than a real reading.
const REPLIES: Record<RishiTone, Record<Language, string[]>> = {
  direct: {
    en: [
      "I can't reach your real chart data right now, so I won't guess at it — that would just be making things up. Try again in a moment.",
      "No shortcuts here — I only answer from your actual computed chart, and I can't reach it just now. Please retry.",
      'Rather than give you a generic guess dressed up as a reading, I\'ll wait until I can actually see your chart again. Try once more.',
    ],
    hi: [
      'अभी आपकी असली कुंडली का डेटा नहीं मिल पा रहा, इसलिए मैं अंदाज़ा नहीं लगाऊंगा — वह सिर्फ़ मनगढ़ंत होगा। कृपया थोड़ी देर बाद फिर कोशिश करें।',
      'कोई शॉर्टकट नहीं — मैं सिर्फ़ आपकी असली गणना से जवाब देता हूं, और अभी वह नहीं मिल पा रही। कृपया दोबारा भेजें।',
      'एक सामान्य अंदाज़े को सही जवाब की तरह दिखाने के बजाय, मैं तब तक रुकूंगा जब तक आपकी असली कुंडली फिर से दिख न जाए। कृपया दोबारा कोशिश करें।',
    ],
  },
  traditional: {
    en: [
      'The texts teach patience even here — I cannot reach your real chart just this moment, so let us wait rather than guess. Please try again shortly.',
      'A reading given without truly seeing your chart would honor neither of us. Give it a moment and ask again.',
      'Even the old astrologers would rather stay silent than speak without the chart in front of them. Please retry in a little while.',
    ],
    hi: [
      'यहां भी धैर्य की सीख है — अभी आपकी असली कुंडली तक नहीं पहुंच पा रहा, इसलिए अंदाज़ा लगाने के बजाय थोड़ा इंतज़ार करें। कृपया कुछ देर बाद फिर पूछें।',
      'बिना कुंडली देखे दिया गया जवाब न आपके लिए सही होगा, न मेरे लिए। थोड़ी देर रुककर फिर पूछें।',
      'पुराने ज्योतिषी भी कुंडली सामने न होने पर चुप रहना बेहतर मानते थे। कृपया थोड़ी देर बाद दोबारा कोशिश करें।',
    ],
  },
  practical: {
    en: [
      "I can't pull up your real chart data right now — no point giving you generic advice dressed as a reading. Try again in a moment.",
      'For anything career or money related, I only work from your real numbers — which I can\'t reach just now. Please retry shortly.',
      "Let's not waste your time on a guess — reconnect in a moment and I'll answer from your actual chart.",
    ],
    hi: [
      'अभी आपकी असली कुंडली का डेटा नहीं मिल पा रहा — सामान्य सलाह को पढ़ने जैसा जवाब देने का कोई फ़ायदा नहीं। कृपया थोड़ी देर बाद फिर कोशिश करें।',
      'करियर या पैसों से जुड़ी किसी भी बात के लिए, मैं सिर्फ़ आपके असली आंकड़ों से काम करता हूं — जो अभी नहीं मिल पा रहे। कृपया थोड़ी देर बाद दोबारा भेजें।',
      'अंदाज़े में आपका समय बर्बाद नहीं करते — थोड़ी देर बाद दोबारा जुड़ें, मैं आपकी असली कुंडली से जवाब दूंगा।',
    ],
  },
  spiritual: {
    en: [
      "This silence is not a bad omen — it's simply that I can't see your real chart right now. Try reaching out again in a moment.",
      "Even a pause has its place. Give it a little time, and ask again once I can truly see your chart.",
      "I'd rather sit in honest silence than offer you words that don't come from your actual chart. Please try again shortly.",
    ],
    hi: [
      'यह चुप्पी कोई अशुभ संकेत नहीं — बस इतना है कि अभी आपकी असली कुंडली मुझे दिख नहीं पा रही। थोड़ी देर बाद फिर से संपर्क करें।',
      'एक ठहराव का भी अपना स्थान है। थोड़ा समय दें, और जब मैं आपकी कुंडली सच में देख पाऊं तब फिर पूछें।',
      'मैं ईमानदार चुप्पी में रहना बेहतर मानता हूं, बजाय ऐसे शब्दों के जो आपकी असली कुंडली से न आए हों। कृपया थोड़ी देर बाद फिर कोशिश करें।',
    ],
  },
  analytical: {
    en: [
      "I can't retrieve your computed chart data at this moment — without it, any answer would be unverifiable, so I'd rather not guess. Please retry.",
      'Cross-referencing requires the real data, which is unavailable right now. Try reconnecting in a moment.',
      "There's no reliable basis for an answer without your actual chart in front of me right now. Please try again shortly.",
    ],
    hi: [
      'अभी आपकी गणना की गई कुंडली का डेटा नहीं मिल पा रहा — इसके बिना कोई भी जवाब सत्यापित नहीं किया जा सकता, इसलिए अंदाज़ा नहीं लगाऊंगा। कृपया दोबारा कोशिश करें।',
      'तुलना के लिए असली डेटा चाहिए, जो अभी उपलब्ध नहीं है। कृपया थोड़ी देर बाद दोबारा जुड़ें।',
      'अभी आपकी असली कुंडली सामने न होने पर किसी भी जवाब का कोई ठोस आधार नहीं है। कृपया थोड़ी देर बाद फिर कोशिश करें।',
    ],
  },
  general: {
    en: [
      "I can't reach your real chart data right now, so I won't guess at an answer — that would just be making things up. Try again in a moment.",
      "Whatever you're asking about, I only answer from your actual computed chart, and I can't reach it just now. Please retry.",
      "Rather than give you a generic answer dressed up as a reading, I'll wait until I can see your chart again. Try once more shortly.",
    ],
    hi: [
      'अभी आपकी असली कुंडली का डेटा नहीं मिल पा रहा, इसलिए मैं अंदाज़ा नहीं लगाऊंगा — वह सिर्फ़ मनगढ़ंत होगा। कृपया थोड़ी देर बाद फिर कोशिश करें।',
      'आप जो भी पूछ रहे हैं, मैं सिर्फ़ आपकी असली गणना से जवाब देता हूं, और अभी वह नहीं मिल पा रही। कृपया दोबारा कोशिश करें।',
      'एक सामान्य जवाब को असली रीडिंग की तरह दिखाने के बजाय, मैं तब तक रुकूंगा जब तक आपकी असली कुंडली फिर से दिख न जाए। कृपया थोड़ी देर बाद फिर कोशिश करें।',
    ],
  },
};

export function getRishiReply(tone: RishiTone, messageIndex: number, language: Language): string {
  const pool = REPLIES[tone][language];
  return pool[messageIndex % pool.length];
}
