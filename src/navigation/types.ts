export type MainTabParamList = {
  HomeTab: undefined;
  KundaliTab: undefined;
  VoiceTab: undefined;
  ChartsTab: undefined;
  ProfileTab: undefined;
};

export type RishiStackParamList = {
  // rishiId is optional — RishiChatScreen defaults to the generalist Vyasa
  // persona (see DEFAULT_RISHI_ID) when no specific Rishi is requested.
  RishiChat: { rishiId?: string } | undefined;
};

export type RootStackParamList = {
  Welcome: undefined;
  AppInfo: undefined;
  Auth: undefined;
  BirthData: undefined;
  AiProcessing: undefined;
  Validation: undefined;
  Preferences: undefined;
  MainTabs: undefined;
  Insights: undefined;
  ManglikAnalysis: undefined;
  UpgradePlans: undefined;
  HoroscopeDetail: undefined;
  PassStore: undefined;
  Payment: { passId: string };
  PeriodAnalysis: undefined;
  GunaMilan: undefined;
};
