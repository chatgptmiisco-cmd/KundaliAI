import { Alert, Platform } from 'react-native';

export interface AlertButtonDef {
  text?: string;
  onPress?: () => void;
  style?: 'default' | 'cancel' | 'destructive';
}

// React Native's own Alert.alert() has NO effect at all on web — see
// node_modules/react-native-web/src/exports/Alert, whose entire
// implementation is `static alert() {}`. Every call site in this app used
// to call Alert.alert directly, which meant every error message,
// confirmation dialog, and "coming soon" notice silently did nothing when
// testing via `expo start --web` — found via a real report ("login button
// isn't working": the login WAS being rejected correctly, the user just
// never saw why). `window.alert`/`window.confirm` are the only real
// cross-browser primitives available here, so this wraps them behind the
// exact same call shape as Alert.alert to keep every existing call site a
// one-line swap.
export function showAlert(title: string, message?: string, buttons?: AlertButtonDef[]): void {
  if (Platform.OS !== 'web') {
    Alert.alert(title, message, buttons as Parameters<typeof Alert.alert>[2]);
    return;
  }

  const fullMessage = message ? `${title}\n\n${message}` : title;

  if (!buttons || buttons.length <= 1) {
    window.alert(fullMessage);
    buttons?.[0]?.onPress?.();
    return;
  }

  // Every multi-button alert in this app is a simple Cancel + one action
  // confirmation — window.confirm's OK/Cancel maps onto that directly.
  // (A 3+ button alert would need a real modal; none exist today.)
  const cancelButton = buttons.find((b) => b.style === 'cancel');
  const actionButton = buttons.find((b) => b !== cancelButton) ?? buttons[buttons.length - 1];
  if (window.confirm(fullMessage)) {
    actionButton?.onPress?.();
  } else {
    cancelButton?.onPress?.();
  }
}
