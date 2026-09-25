import React from 'react';
import { StyleSheet, View, ViewProps } from 'react-native';
import useIsWideScreen from '../hooks/useIsWideScreen';
import { spacing } from '../theme/theme';

const MAX_CONTENT_WIDTH = 1040;

// Centers a screen's content with a max width and breathing room on a wide
// (desktop-class) viewport; a plain passthrough below the breakpoint, so
// every screen this wraps keeps its existing phone layout byte-for-byte.
// Deliberately just a width/centering shell — it doesn't touch spacing,
// cards, or anything else about what it wraps.
export default function WebPageContainer({ children, style, ...rest }: ViewProps) {
  const isWide = useIsWideScreen();
  if (!isWide) {
    return (
      <View style={style} {...rest}>
        {children}
      </View>
    );
  }
  return (
    // Caught live: every caller passes `style={{flex: 1}}` meaning "fill
    // the screen" (so the ScrollView inside can compute a bounded, actually
    // scrollable height) — the narrow-screen branch above applies it
    // directly and works fine, but this wide-screen branch only ever
    // forwarded `style` to `inner`, never to `outer`. Without flex:1,
    // `outer` doesn't stretch to fill ITS OWN parent's height on web, so
    // `inner`'s flex:1 (and the ScrollView's, inside that) has no bounded
    // height to flex within — the whole page just grows to content height
    // instead of scrolling internally, and gets clipped by the navigator's
    // own overflow:hidden screen container. Applied to both views now, the
    // same way the narrow branch already applies it to its one view.
    <View style={[styles.outer, style]} {...rest}>
      <View style={[styles.inner, style]}>{children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  outer: {
    width: '100%',
    alignItems: 'center',
  },
  inner: {
    width: '100%',
    maxWidth: MAX_CONTENT_WIDTH,
    paddingHorizontal: spacing.lg,
  },
});
