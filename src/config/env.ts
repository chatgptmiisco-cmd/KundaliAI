// Backend base URL. Update the host if your dev machine's LAN IP changes
// (check with `ipconfig` on Windows) — the phone and this machine must be on
// the same Wi-Fi network for Expo Go to reach it.
export const API_BASE_URL = 'http://192.168.1.59:8000/api/v1';

// Every subscription-gated feature (D9/D10, unlimited period analyses, real
// AI chat replies, PDF download, voice narration) is unlocked for everyone
// while pricing isn't live yet. The backend has the matching
// ALL_FEATURES_FREE setting (see backend/.env.example) — flip both back to
// false together when plans launch.
export const ALL_FEATURES_FREE = true;
