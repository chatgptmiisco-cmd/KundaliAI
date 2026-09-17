// Backend base URL. Currently pointed at a temporary ngrok tunnel so the
// team can test from anywhere (no shared Wi-Fi needed). The tunnel only
// lives as long as the ngrok process on the dev machine stays running —
// swap back to the LAN IP (http://192.168.1.59:8000/api/v1, check with
// `ipconfig` on Windows) for normal local development.
export const API_BASE_URL = 'https://5ff0-2401-4900-5f72-cc68-c04b-527a-7f31-c2e2.ngrok-free.app/api/v1';

// Every subscription-gated feature (D9/D10, unlimited period analyses, real
// AI chat replies, PDF download, voice narration) is unlocked for everyone
// while pricing isn't live yet. The backend has the matching
// ALL_FEATURES_FREE setting (see backend/.env.example) — flip both back to
// false together when plans launch.
export const ALL_FEATURES_FREE = true;
