import { Language, RishiTone } from '../types/kundali';

// Canned reply pools per persona tone, cycled by message index. This stands
// in for a real LLM-backed astrologer chat — swap for a real API call once
// the backend chat endpoint exists, keeping the same (tone, index, language)
// signature so screens don't need to change.
const REPLIES: Record<RishiTone, Record<Language, string[]>> = {
  direct: {
    en: [
      'Your Moon is in Cancer and your Lagna in Taurus — that combination makes you steadier than most, but slower to act than you should be. Don\'t mistake caution for wisdom every time.',
      'Mars in the 7th is doing exactly what it always does — it does not ruin a marriage on its own, but it does demand honesty in the relationship you\'re avoiding right now.',
      'Your current Mahadasha rewards discipline, not shortcuts. If you\'re looking for a quick fix this period, you won\'t find one here — and pretending otherwise won\'t help you.',
    ],
    hi: [
      'आपका चंद्र कर्क में है और लग्न वृषभ में — यह मेल आपको ज़्यादातर लोगों से स्थिर बनाता है, पर ज़रूरत से ज़्यादा धीमा भी। सावधानी को हमेशा समझदारी मत समझिए।',
      'सातवें भाव का मंगल वही कर रहा है जो हमेशा करता है — यह अकेले शादी नहीं बिगाड़ता, पर जिस रिश्ते से आप बच रहे हैं, वहां ईमानदारी मांगता है।',
      'आपकी मौजूदा महादशा अनुशासन का फल देती है, शॉर्टकट का नहीं। अगर इस दौर में जल्दी हल ढूंढ रहे हैं, तो यहां नहीं मिलेगा — और खुद को झुठलाने से फ़ायदा नहीं होगा।',
    ],
  },
  traditional: {
    en: [
      'This placement has been understood the same way for generations — it asks for patience, not fear. Trust the process a little longer.',
      'Every dasha brings its own lesson. This one is teaching steadiness, and it will pass in its own time.',
      'Traditional texts would call this a testing period, not a bad one. There is a difference, and it matters.',
    ],
    hi: [
      'यह स्थिति पीढ़ियों से इसी तरह समझी जाती रही है — यह धैर्य मांगती है, डर नहीं। थोड़ी और श्रद्धा रखें।',
      'हर दशा अपना सबक लाती है। यह दशा स्थिरता सिखा रही है, और अपने समय पर बीत जाएगी।',
      'शास्त्रों में इसे परीक्षा का समय कहा जाएगा, बुरा समय नहीं। इसमें फ़र्क़ है, और यह मायने रखता है।',
    ],
  },
  practical: {
    en: [
      'For career purposes, this period rewards consolidation over expansion — strengthen what you have before starting something new.',
      'Financially, this is a save-and-plan window, not a spend-and-hope one. The numbers in your chart support patience here.',
      'If you\'re weighing a job change, wait for the next few months to settle before deciding — the timing improves.',
    ],
    hi: [
      'करियर के लिहाज़ से, यह दौर विस्तार से ज़्यादा मज़बूती का इनाम देता है — नया शुरू करने से पहले जो है उसे मज़बूत करें।',
      'आर्थिक रूप से, यह बचत और योजना बनाने का समय है, खर्च और उम्मीद का नहीं। आपकी कुंडली के आंकड़े धैर्य का समर्थन करते हैं।',
      'अगर नौकरी बदलने पर विचार कर रहे हैं, तो अगले कुछ महीने स्थिर होने दें — समय बेहतर होगा।',
    ],
  },
  spiritual: {
    en: [
      'This difficulty is not punishment — it is redirection. Something in your pattern is ready to change, and the chart is simply pointing at it.',
      'A simple, consistent practice — even five quiet minutes a day — will do more for this period than any single remedy.',
      'What looks like an obstacle here is often the exact thing that clears the way, once you stop resisting it.',
    ],
    hi: [
      'यह कठिनाई सज़ा नहीं है — यह दिशा बदलने का इशारा है। आपके पैटर्न में कुछ बदलने के लिए तैयार है, और कुंडली बस उसी ओर इशारा कर रही है।',
      'एक सरल, नियमित अभ्यास — दिन में पांच शांत मिनट भी — इस दौर में किसी भी एक उपाय से ज़्यादा काम करेगा।',
      'जो यहां रुकावट लगती है, वही अक्सर रास्ता खोलने वाली चीज़ होती है, बस विरोध करना छोड़ना होगा।',
    ],
  },
  analytical: {
    en: [
      'Using Lahiri ayanamsa, your Lagna sits at the very start of its sign — a strong placement that sharpens both its strengths and its weaknesses.',
      'The current Antardasha lord is placed in a whole-sign kendra from the Moon, which technically supports steady, if slow, progress.',
      'Cross-referencing the transit of Saturn with your natal chart, the next few months activate your 10th house — professionally significant, worth tracking closely.',
    ],
    hi: [
      'लाहिड़ी अयनांश के अनुसार, आपका लग्न अपनी राशि की शुरुआत में है — यह एक मज़बूत स्थिति है जो गुण और चुनौती दोनों को तेज़ करती है।',
      'मौजूदा अंतर्दशा का स्वामी चंद्रमा से होल-साइन केंद्र में स्थित है, जो तकनीकी रूप से स्थिर, भले धीमी, प्रगति का समर्थन करता है।',
      'शनि के गोचर को जन्म कुंडली से मिलाने पर, अगले कुछ महीने आपके दसवें भाव को सक्रिय करते हैं — पेशेवर रूप से महत्वपूर्ण, ध्यान से देखने लायक।',
    ],
  },
};

export function getRishiReply(tone: RishiTone, messageIndex: number, language: Language): string {
  const pool = REPLIES[tone][language];
  return pool[messageIndex % pool.length];
}
