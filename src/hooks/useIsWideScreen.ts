import { useWindowDimensions } from 'react-native';

// The one breakpoint this app draws on for "desktop-appropriate layout" vs
// "phone layout" — 900px comfortably fits a persistent sidebar plus a
// max-width content column (see WebPageContainer) without cramping either,
// while staying well clear of large-phone/small-tablet widths that should
// still get the phone layout. No tablet-specific tier: this app only ever
// needs the binary "is there room for a desktop shell" answer.
const WIDE_SCREEN_BREAKPOINT = 900;

export default function useIsWideScreen(): boolean {
  const { width } = useWindowDimensions();
  return width >= WIDE_SCREEN_BREAKPOINT;
}
