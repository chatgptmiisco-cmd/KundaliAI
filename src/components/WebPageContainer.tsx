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
    <View style={styles.outer} {...rest}>
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
