import React from 'react';
import { StyleSheet, View } from 'react-native';
import PlanetLoader from './PlanetLoader';
import { spacing } from '../theme/theme';

export default function LoadingState({ message }: { message: string }) {
  return (
    <View style={styles.wrap}>
      <PlanetLoader size={84} message={message} />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
  },
});
