import { useNavigation } from '@react-navigation/native';
import React, { useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { login, requestOtp, signup, verifyOtp } from '../api/client';
import PrimaryButton from '../components/PrimaryButton';
import { useUserStore } from '../store/useUserStore';
import { colors, radius, spacing, typography } from '../theme/theme';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PHONE_RE = /^\+?[1-9]\d{7,14}$/;

interface FieldErrors {
  name?: string;
  email?: string;
  password?: string;
  confirmPassword?: string;
  phone?: string;
  otp?: string;
}

export default function AuthScreen() {
  const { t } = useTranslation();
  const navigation = useNavigation<any>();
  const language = useUserStore((s) => s.language);
  const setAuthSession = useUserStore((s) => s.setAuthSession);
  const [mode, setMode] = useState<'signup' | 'login'>('signup');
  const [method, setMethod] = useState<'email' | 'phone'>('email');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [phone, setPhone] = useState('');
  const [otpCode, setOtpCode] = useState('');
  const [otpSent, setOtpSent] = useState(false);
  const [devOtpCode, setDevOtpCode] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});

  const clearError = (key: keyof FieldErrors) => {
    setErrors((prev) => (prev[key] ? { ...prev, [key]: undefined } : prev));
  };

  const handleContinue = async () => {
    const nextErrors: FieldErrors = {};
    if (mode === 'signup' && !name.trim()) {
      nextErrors.name = t('onboarding.errorNameRequired');
    }
    if (!EMAIL_RE.test(email.trim())) {
      nextErrors.email = t('onboarding.errorEmailInvalid');
    }
    if (password.length < 8) {
      nextErrors.password = t('onboarding.errorPasswordLength');
    }
    if (mode === 'signup' && confirmPassword !== password) {
      nextErrors.confirmPassword = t('onboarding.errorPasswordMismatch');
    }
    setErrors(nextErrors);
    if (Object.values(nextErrors).some(Boolean)) return;

    setSubmitting(true);
    try {
      const contentLanguage = language === 'hi' ? 'hi' : 'en';
      const result =
        mode === 'signup'
          ? await signup(email.trim(), password, name.trim(), contentLanguage)
          : await login(email.trim(), password);
      setAuthSession(result.accessToken, email.trim());
      navigation.navigate('BirthData');
    } catch (err: any) {
      if (mode === 'signup' && err?.status === 409) {
        Alert.alert(t('onboarding.accountExistsTitle'), t('onboarding.accountExistsMessage'), [
          { text: t('common.cancel'), style: 'cancel' },
          {
            text: t('onboarding.loginTab'),
            onPress: () => {
              setMode('login');
              setPassword('');
              setConfirmPassword('');
            },
          },
        ]);
      } else if (mode === 'login' && err?.status === 401) {
        Alert.alert(t('common.tryAgain'), t('onboarding.errorInvalidCredentials'));
      } else {
        Alert.alert(t('common.tryAgain'), err?.message ?? String(err));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleSendOtp = async () => {
    if (!PHONE_RE.test(phone.trim())) {
      setErrors((prev) => ({ ...prev, phone: t('onboarding.errorPhoneInvalid') }));
      return;
    }
    setErrors((prev) => ({ ...prev, phone: undefined }));
    setSubmitting(true);
    try {
      const result = await requestOtp(phone.trim());
      setOtpSent(true);
      setDevOtpCode(result.devCode);
    } catch (err: any) {
      Alert.alert(t('common.tryAgain'), err?.message ?? String(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleVerifyOtp = async () => {
    if (!/^\d{6}$/.test(otpCode.trim())) {
      setErrors((prev) => ({ ...prev, otp: t('onboarding.errorOtpInvalid') }));
      return;
    }
    setErrors((prev) => ({ ...prev, otp: undefined }));
    setSubmitting(true);
    try {
      const result = await verifyOtp(phone.trim(), otpCode.trim());
      setAuthSession(result.accessToken, phone.trim());
      navigation.navigate('BirthData');
    } catch (err: any) {
      Alert.alert(t('common.tryAgain'), err?.message ?? String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={styles.title}>{t('onboarding.authTitle')}</Text>
      <Text style={styles.subtitle}>
        {mode === 'signup' ? t('onboarding.authSubtitleSignup') : t('onboarding.authSubtitleLogin')}
      </Text>

      <View style={styles.tabs}>
        <Pressable
          onPress={() => {
            setMode('signup');
            setErrors({});
          }}
          style={[styles.tab, mode === 'signup' && styles.tabActive]}
        >
          <Text style={[styles.tabText, mode === 'signup' && styles.tabTextActive]}>
            {t('onboarding.signupTab')}
          </Text>
        </Pressable>
        <Pressable
          onPress={() => {
            setMode('login');
            setErrors({});
          }}
          style={[styles.tab, mode === 'login' && styles.tabActive]}
        >
          <Text style={[styles.tabText, mode === 'login' && styles.tabTextActive]}>
            {t('onboarding.loginTab')}
          </Text>
        </Pressable>
      </View>

      <View style={styles.methodTabs}>
        <Pressable
          onPress={() => {
            setMethod('email');
            setErrors({});
          }}
          style={[styles.methodTab, method === 'email' && styles.methodTabActive]}
        >
          <Text style={[styles.methodTabText, method === 'email' && styles.methodTabTextActive]}>
            {t('onboarding.methodEmail')}
          </Text>
        </Pressable>
        <Pressable
          onPress={() => {
            setMethod('phone');
            setErrors({});
          }}
          style={[styles.methodTab, method === 'phone' && styles.methodTabActive]}
        >
          <Text style={[styles.methodTabText, method === 'phone' && styles.methodTabTextActive]}>
            {t('onboarding.methodPhone')}
          </Text>
        </Pressable>
      </View>

      {method === 'email' ? (
        <>
          {mode === 'signup' && (
            <Field
              label={t('profile.nameLabel')}
              value={name}
              onChangeText={(v) => {
                setName(v);
                clearError('name');
              }}
              error={errors.name}
            />
          )}
          <Field
            label={t('onboarding.emailLabel')}
            value={email}
            onChangeText={(v) => {
              setEmail(v);
              clearError('email');
            }}
            keyboardType="email-address"
            error={errors.email}
          />
          <Field
            label={t('onboarding.passwordLabel')}
            value={password}
            onChangeText={(v) => {
              setPassword(v);
              clearError('password');
            }}
            secureTextEntry
            error={errors.password}
          />
          {mode === 'signup' && (
            <Field
              label={t('onboarding.confirmPasswordLabel')}
              value={confirmPassword}
              onChangeText={(v) => {
                setConfirmPassword(v);
                clearError('confirmPassword');
              }}
              secureTextEntry
              error={errors.confirmPassword}
            />
          )}

          <View style={styles.spacer} />
          <PrimaryButton
            label={t('onboarding.continueButton')}
            onPress={handleContinue}
            loading={submitting}
            disabled={submitting}
          />
        </>
      ) : (
        <>
          <Field
            label={t('onboarding.phoneLabel')}
            value={phone}
            onChangeText={(v) => {
              setPhone(v);
              clearError('phone');
            }}
            keyboardType="phone-pad"
            editable={!otpSent}
            error={errors.phone}
          />

          {otpSent && (
            <>
              <Text style={styles.otpSentNote}>
                {t('onboarding.otpSentTo', { phone: phone.trim() })}
              </Text>
              {devOtpCode && (
                <Text style={styles.devOtpNote}>{t('onboarding.devOtpNote', { code: devOtpCode })}</Text>
              )}
              <Field
                label={t('onboarding.otpLabel')}
                value={otpCode}
                onChangeText={(v) => {
                  setOtpCode(v);
                  clearError('otp');
                }}
                keyboardType="number-pad"
                error={errors.otp}
              />
            </>
          )}

          <View style={styles.spacer} />
          {!otpSent ? (
            <PrimaryButton
              label={t('onboarding.sendOtpButton')}
              onPress={handleSendOtp}
              loading={submitting}
              disabled={submitting}
            />
          ) : (
            <>
              <PrimaryButton
                label={t('onboarding.verifyOtpButton')}
                onPress={handleVerifyOtp}
                loading={submitting}
                disabled={submitting}
              />
              <PrimaryButton
                label={t('onboarding.resendOtpButton')}
                variant="outline"
                onPress={handleSendOtp}
                disabled={submitting}
              />
            </>
          )}
        </>
      )}
    </ScrollView>
  );
}

function Field({
  label,
  value,
  onChangeText,
  secureTextEntry,
  keyboardType,
  editable = true,
  error,
}: {
  label: string;
  value: string;
  onChangeText: (v: string) => void;
  secureTextEntry?: boolean;
  keyboardType?: 'default' | 'email-address' | 'phone-pad' | 'number-pad';
  editable?: boolean;
  error?: string;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        style={[styles.input, !editable && styles.inputDisabled, !!error && styles.inputError]}
        secureTextEntry={secureTextEntry}
        keyboardType={keyboardType}
        autoCapitalize="none"
        editable={editable}
        placeholderTextColor={colors.textSecondary}
      />
      {!!error && (
        <Text style={styles.errorText} accessibilityRole="alert">
          {error}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  content: {
    padding: spacing.md,
    paddingBottom: spacing.xxl,
  },
  title: {
    ...typography.title,
    color: colors.textPrimary,
    marginBottom: spacing.xs,
  },
  subtitle: {
    ...typography.body,
    color: colors.textSecondary,
    marginBottom: spacing.md,
  },
  tabs: {
    flexDirection: 'row',
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.md,
    padding: spacing.xs,
    marginBottom: spacing.lg,
  },
  tab: {
    flex: 1,
    minHeight: 48,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.sm,
  },
  tabActive: {
    backgroundColor: colors.primary,
  },
  tabText: {
    ...typography.bodyBold,
    color: colors.textSecondary,
  },
  tabTextActive: {
    color: colors.textInverse,
  },
  methodTabs: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  methodTab: {
    flex: 1,
    minHeight: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.sm,
    borderWidth: 1.5,
    borderColor: colors.border,
  },
  methodTabActive: {
    borderColor: colors.primary,
    backgroundColor: colors.surfaceMuted,
  },
  methodTabText: {
    ...typography.caption,
    color: colors.textSecondary,
  },
  methodTabTextActive: {
    color: colors.primary,
  },
  otpSentNote: {
    ...typography.caption,
    color: colors.textSecondary,
    marginBottom: spacing.sm,
  },
  devOtpNote: {
    ...typography.caption,
    color: colors.premium,
    marginBottom: spacing.sm,
  },
  field: {
    marginBottom: spacing.md,
  },
  fieldLabel: {
    ...typography.caption,
    color: colors.textSecondary,
    marginBottom: spacing.xs,
  },
  input: {
    ...typography.body,
    color: colors.textPrimary,
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    minHeight: 48,
    backgroundColor: colors.background,
  },
  inputDisabled: {
    backgroundColor: colors.surfaceMuted,
    color: colors.textSecondary,
  },
  inputError: {
    borderColor: colors.accent,
  },
  errorText: {
    ...typography.caption,
    color: colors.accentDark,
    marginTop: spacing.xs,
  },
  spacer: {
    height: spacing.lg,
  },
});
