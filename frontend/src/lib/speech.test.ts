import { afterEach, describe, expect, it, vi } from "vitest";
import { listen, speechSupported } from "./speech";

describe("speech", () => {
  afterEach(() => {
    delete (window as unknown as Record<string, unknown>).webkitSpeechRecognition;
  });

  it("reports missing support and fails softly", () => {
    expect(speechSupported()).toBe(false);
    const done = vi.fn();
    listen("en", () => undefined, done);
    expect(done).toHaveBeenCalledWith("Voice input is not supported in this browser.");
  });

  it("uses the Indian locale for the chosen language and passes the transcript", () => {
    const started: { lang: string }[] = [];
    class FakeRecognition {
      lang = "";
      interimResults = false;
      continuous = true;
      onresult: ((event: unknown) => void) | null = null;
      onend: (() => void) | null = null;
      onerror: (() => void) | null = null;
      start() {
        started.push(this);
        this.onresult?.({ resultIndex: 0, results: [{ isFinal: true, 0: { transcript: "fix my loop " } }] });
        this.onend?.();
      }
      stop() {}
    }
    (window as unknown as Record<string, unknown>).webkitSpeechRecognition = FakeRecognition;

    const onText = vi.fn();
    const onDone = vi.fn();
    listen("kn", onText, onDone);
    expect(started[0].lang).toBe("kn-IN");
    expect(onText).toHaveBeenCalledWith("fix my loop");
    expect(onDone).toHaveBeenCalled();
  });
});
