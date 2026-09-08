import * as Speech from 'expo-speech';
import { create } from 'zustand';
import { Language } from '../types/kundali';

// Stand-in for the real backend TTS/audio-streaming endpoints: on-device
// speech synthesis via expo-speech, so voice features are testable in Expo
// Go with no server. Swap `Speech.speak` for a real streamed-audio player
// (expo-av) once `/voice/tts` returns an audio URL — that will also unlock
// true pause/resume/seek, which on-device TTS cannot reliably offer.

const WORDS_PER_SECOND = 2.3;
// Slightly slower and a touch lower-pitched than the platform default, which
// otherwise reads as rushed and flat — calmer pacing matters most for the
// senior audience this app is built for.
const SPEECH_RATE = 0.85;
const SPEECH_PITCH = 0.96;
let tickHandle: ReturnType<typeof setInterval> | null = null;

interface VoiceState {
  visible: boolean;
  title: string;
  text: string;
  language: Language;
  playing: boolean;
  elapsed: number;
  duration: number;
  play: (args: { title: string; text: string; language: Language }) => void;
  toggle: () => void;
  close: () => void;
}

function clearTick() {
  if (tickHandle) {
    clearInterval(tickHandle);
    tickHandle = null;
  }
}

function startSpeaking(get: () => VoiceState, set: (partial: Partial<VoiceState>) => void) {
  const { text, language, duration } = get();
  clearTick();
  Speech.speak(text, {
    language: language === 'hi' ? 'hi-IN' : 'en-IN',
    rate: SPEECH_RATE,
    pitch: SPEECH_PITCH,
    onDone: () => {
      clearTick();
      set({ playing: false, elapsed: get().duration });
    },
    onStopped: () => clearTick(),
    onError: () => {
      clearTick();
      set({ playing: false });
    },
  });
  tickHandle = setInterval(() => {
    const state = get();
    if (!state.playing) return;
    if (state.elapsed >= duration) {
      clearTick();
      return;
    }
    set({ elapsed: state.elapsed + 1 });
  }, 1000);
}

export const useVoiceStore = create<VoiceState>((set, get) => ({
  visible: false,
  title: '',
  text: '',
  language: 'en',
  playing: false,
  elapsed: 0,
  duration: 0,

  play: ({ title, text, language }) => {
    Speech.stop();
    clearTick();
    const wordCount = text.trim().split(/\s+/).length;
    const duration = Math.max(3, Math.round(wordCount / (WORDS_PER_SECOND * SPEECH_RATE)));

    set({ visible: true, title, text, language, playing: true, elapsed: 0, duration });
    startSpeaking(get, set);
  },

  toggle: () => {
    const { playing } = get();
    if (playing) {
      Speech.stop();
      clearTick();
      set({ playing: false });
    } else {
      // On-device TTS cannot resume mid-utterance, so restart the clip.
      set({ playing: true, elapsed: 0 });
      startSpeaking(get, set);
    }
  },

  close: () => {
    Speech.stop();
    clearTick();
    set({ visible: false, playing: false, elapsed: 0, duration: 0, title: '', text: '' });
  },
}));
