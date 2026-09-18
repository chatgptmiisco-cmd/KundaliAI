// Product spec §1-2 — right after birth data, ask ONE topic-pick question,
// then 2-4 high-value follow-ups for that topic (never a full form). Each
// question is deliberately short and conversational, matching the spec's
// own career example, and answers get sent as free text to the backend's
// structured-extraction endpoint (see api/client.submitOnboardingContext)
// rather than parsed into fixed fields here.
export type OnboardingTopic =
  | 'career' | 'business' | 'relationships' | 'marriage' | 'money' | 'family' | 'personalDirection' | 'other';

export const ONBOARDING_TOPICS: { key: OnboardingTopic; icon: string; labelKey: string; questionKeys: string[] }[] = [
  { key: 'career', icon: 'briefcase-outline', labelKey: 'onboardingTopics.career', questionKeys: [
    'onboardingTopics.q.career.0', 'onboardingTopics.q.career.1', 'onboardingTopics.q.career.2',
  ] },
  { key: 'business', icon: 'trending-up-outline', labelKey: 'onboardingTopics.business', questionKeys: [
    'onboardingTopics.q.business.0', 'onboardingTopics.q.business.1', 'onboardingTopics.q.business.2',
  ] },
  { key: 'relationships', icon: 'heart-outline', labelKey: 'onboardingTopics.relationships', questionKeys: [
    'onboardingTopics.q.relationships.0', 'onboardingTopics.q.relationships.1',
  ] },
  { key: 'marriage', icon: 'people-outline', labelKey: 'onboardingTopics.marriage', questionKeys: [
    'onboardingTopics.q.marriage.0', 'onboardingTopics.q.marriage.1',
  ] },
  { key: 'money', icon: 'cash-outline', labelKey: 'onboardingTopics.money', questionKeys: [
    'onboardingTopics.q.money.0', 'onboardingTopics.q.money.1',
  ] },
  { key: 'family', icon: 'home-outline', labelKey: 'onboardingTopics.family', questionKeys: [
    'onboardingTopics.q.family.0', 'onboardingTopics.q.family.1',
  ] },
  { key: 'personalDirection', icon: 'compass-outline', labelKey: 'onboardingTopics.personalDirection', questionKeys: [
    'onboardingTopics.q.personalDirection.0', 'onboardingTopics.q.personalDirection.1',
  ] },
  { key: 'other', icon: 'ellipsis-horizontal-outline', labelKey: 'onboardingTopics.other', questionKeys: [
    'onboardingTopics.q.other.0',
  ] },
];

// The backend's `topic` field is a plain slug, not this screen's i18n key.
export const TOPIC_SLUG: Record<OnboardingTopic, string> = {
  career: 'career', business: 'business', relationships: 'relationships', marriage: 'marriage',
  money: 'money', family: 'family', personalDirection: 'personal_direction', other: 'other',
};
