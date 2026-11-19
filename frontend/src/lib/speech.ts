/** Small wrapper around the browser's Web Speech API (Chrome, Edge, Safari). */

export type SpeechLanguage = "en" | "kn" | "hi";

const LOCALES: Record<SpeechLanguage, string> = { en: "en-IN", kn: "kn-IN", hi: "hi-IN" };

interface SpeechResultEvent {
  resultIndex: number;
  results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }>;
}

interface Recognizer {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: SpeechResultEvent) => void) | null;
  onend: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  start: () => void;
  stop: () => void;
}

type RecognizerClass = new () => Recognizer;

function recognizerClass(): RecognizerClass | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: RecognizerClass; webkitSpeechRecognition?: RecognizerClass };
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

export function speechSupported(): boolean {
  return recognizerClass() !== null;
}

/**
 * Start listening. `onText` gets the full transcript so far (final + interim),
 * `onDone` fires when the browser stops. Returns a stop function.
 */
export function listen(
  language: SpeechLanguage,
  onText: (text: string) => void,
  onDone: (error?: string) => void,
): () => void {
  const Recognition = recognizerClass();
  if (!Recognition) {
    onDone("Voice input is not supported in this browser.");
    return () => undefined;
  }
  const recognizer = new Recognition();
  recognizer.lang = LOCALES[language];
  recognizer.interimResults = true;
  recognizer.continuous = false;

  recognizer.onresult = (event) => {
    let text = "";
    for (let i = 0; i < event.results.length; i += 1) {
      text += event.results[i][0].transcript;
    }
    onText(text.trim());
  };
  recognizer.onerror = (event) => {
    onDone(event.error === "not-allowed" ? "Microphone permission was denied." : undefined);
  };
  recognizer.onend = () => onDone();
  recognizer.start();
  return () => recognizer.stop();
}
