export type AnalyticsEvent =
  | 'complete_kundali_viewed'
  | 'manglik_details_viewed'
  | 'voice_explanation_played';

interface EventProps {
  [key: string]: string | number | boolean | undefined;
}

// Stub analytics sink. Swap the console.log below for a real provider
// (Segment, Firebase, Amplitude, etc.) without touching call sites.
export function trackEvent(event: AnalyticsEvent, props?: EventProps) {
  console.log(`[analytics] ${event}`, props ?? {});
}
