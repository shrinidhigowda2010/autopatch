import { useEffect, useRef, type FormEvent, type KeyboardEvent } from "react";
import { motion } from "framer-motion";
import { MicIcon, PlusIcon, SendIcon } from "./icons";

export type ChatMode = "auto" | "explain" | "fix" | "review";

export const MODES: { value: ChatMode; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: "explain", label: "Explain" },
  { value: "fix", label: "Fix" },
  { value: "review", label: "Review" },
];

const ATTACH_TYPES =
  ".py,.js,.jsx,.ts,.tsx,.java,.c,.cpp,.h,.cs,.go,.rs,.rb,.php,.kt,.swift,.sql,.html,.css,.json,.txt,.md,.ipynb,.pdf,.docx,.png,.jpg,.jpeg,.webp";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  mode: ChatMode;
  onModeChange: (mode: ChatMode) => void;
  onAttach: (file: File) => void;
  onMic: () => void;
  listening: boolean;
  micSupported: boolean;
  busy: boolean;
  attaching: boolean;
  large?: boolean;
}

/** The rounded input pill. Shared between the centred empty state and the bottom bar. */
export default function Composer({
  value,
  onChange,
  onSend,
  mode,
  onModeChange,
  onAttach,
  onMic,
  listening,
  micSupported,
  busy,
  attaching,
  large = false,
}: Props) {
  const textRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Grow with the text, up to a limit.
  useEffect(() => {
    const box = textRef.current;
    if (!box) return;
    box.style.height = "auto";
    box.style.height = `${Math.min(box.scrollHeight, 220)}px`;
  }, [value]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!busy && value.trim()) onSend();
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (!busy && value.trim()) onSend();
    }
  }

  return (
    <motion.form
      layoutId="fixpilot-composer"
      transition={{ type: "spring", stiffness: 260, damping: 30 }}
      onSubmit={submit}
      className={`relative w-full rounded-[28px] border border-line bg-panel shadow-card focus-within:border-ink ${
        large ? "px-4 pb-3 pt-4" : "px-3 pb-2 pt-3"
      }`}
    >
      <textarea
        ref={textRef}
        rows={1}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder={listening ? "Listening…" : "Ask FixPilot about your code…"}
        aria-label="Message FixPilot"
        className={`block w-full resize-none bg-transparent px-1 text-ink placeholder:text-mist focus:outline-none ${
          large ? "text-base" : "text-sm"
        }`}
      />
      <div className="mt-2 flex items-center gap-2">
        <input
          ref={fileRef}
          type="file"
          accept={ATTACH_TYPES}
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) onAttach(file);
            e.target.value = "";
          }}
        />
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={attaching}
          className="grid h-9 w-9 place-items-center rounded-full border border-line text-ink transition hover:border-ink disabled:opacity-60"
          title="Attach a file, PDF or screenshot"
          aria-label="Attach a file"
        >
          {attaching ? <span className="h-3 w-3 animate-spin rounded-full border-2 border-ink border-t-transparent" /> : <PlusIcon />}
        </button>
        <label className="sr-only" htmlFor="fixpilot-mode">
          Mode
        </label>
        <select
          id="fixpilot-mode"
          value={mode}
          onChange={(e) => onModeChange(e.target.value as ChatMode)}
          className="h-9 rounded-full border border-line bg-cream px-3 text-sm font-medium text-ink hover:border-ink focus:outline-none"
        >
          {MODES.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        <div className="ml-auto flex items-center gap-2">
          {micSupported && (
            <button
              type="button"
              onClick={onMic}
              className={`grid h-9 w-9 place-items-center rounded-full border transition ${
                listening ? "animate-pulse border-bug bg-bug text-cream" : "border-line text-ink hover:border-ink"
              }`}
              title={listening ? "Stop listening" : "Speak your question"}
              aria-label={listening ? "Stop voice input" : "Start voice input"}
              aria-pressed={listening}
            >
              <MicIcon />
            </button>
          )}
          <button
            type="submit"
            disabled={busy || !value.trim()}
            className="grid h-9 w-9 place-items-center rounded-full bg-ink text-cream transition hover:-translate-y-px disabled:opacity-40"
            aria-label="Send message"
          >
            <SendIcon />
          </button>
        </div>
      </div>
    </motion.form>
  );
}
