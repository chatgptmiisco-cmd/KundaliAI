export type MainTabParamList = {
  HomeTab: undefined;
  KundaliTab: undefined;
  VoiceTab: undefined;
  ChartsTab: undefined;
  ProfileTab: undefined;
};

export type RishiStackParamList = {
  RishiPicker: undefined;
  RishiChat: { rishiId: string };
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
