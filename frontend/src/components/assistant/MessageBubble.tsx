import { useState } from "react";
import { Link } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import SyntaxHighlighter from "../../lib/highlighter";
import { oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import DiffView from "../DiffView";
import Logo from "../Logo";
import { CheckIcon, CopyIcon, RefreshIcon, ThumbDownIcon, ThumbUpIcon } from "./icons";

export interface ToolStep {
  name: string;
  label: string;
  status: string;
}

export interface PatchCard {
  patch_id: string;
  bug_id: string;
  title: string;
  file: string;
  status: string;
  diff: string;
  before_code: string;
  after_code: string;
  confidence: number;
}

export interface ChatMsg {
  id: string;
  role: "user" | "assistant";
  content: string;
  tool_steps?: ToolStep[];
  patches?: PatchCard[];
  feedback?: number | null;
  streaming?: boolean;
}

interface Props {
  msg: ChatMsg;
  projectId: string;
  canRegenerate: boolean;
  onApprove: (patchId: string) => void;
  onReject: (patchId: string) => void;
  onRegenerate: () => void;
  onFeedback: (value: number) => void;
}

function stepIcon(name: string): string {
  if (name === "run_tests") return "🧪";
  if (name.includes("scan") || name.includes("search")) return "🔍";
  return "✅";
}

export default function MessageBubble({ msg, projectId, canRegenerate, onApprove, onReject, onRegenerate, onFeedback }: Props) {
  const [copied, setCopied] = useState(false);
  const isUser = msg.role === "user";
  const saved = !msg.streaming && !msg.id.startsWith("stream-") && !msg.id.startsWith("local-");

  async function copy() {
    try {
      await navigator.clipboard.writeText(msg.content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  const actionClass = "grid h-8 w-8 place-items-center rounded-full text-ink transition hover:bg-panel";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <p className="max-w-[85%] whitespace-pre-wrap rounded-3xl rounded-br-lg bg-ink px-4 py-2.5 text-sm text-cream shadow-emboss">
          {msg.content}
        </p>
      </div>
    );
  }

  return (
    <div className="flex gap-3">
      <Logo markOnly className="mt-1 h-7 w-auto shrink-0" />
      <div className="min-w-0 flex-1 space-y-2">
        {(msg.tool_steps || []).length > 0 && (
          <div className="flex flex-wrap gap-2">
            {(msg.tool_steps || []).map((step, index) => (
              <span
                key={`${step.name}-${index}`}
                className="rounded-full border border-line bg-panel px-3 py-1 text-xs text-ink"
              >
                {stepIcon(step.name)} {step.label}
              </span>
            ))}
          </div>
        )}

        <div className="text-sm leading-relaxed text-ink">
          {msg.content ? (
            <Markdown body={msg.content} />
          ) : (
            msg.streaming && <ThinkingDots />
          )}
        </div>

        {(msg.patches || []).map((patch) => (
          <div key={patch.patch_id} className="card-3d max-w-2xl p-3">
            <p className="text-sm font-semibold">{patch.title}</p>
            <p className="font-mono text-xs text-mist">
              {patch.file} · {patch.status} · {Math.round(patch.confidence * 100)}% confidence
            </p>
            <div className="mt-2">
              <DiffView before={patch.before_code} after={patch.after_code} diff={patch.diff} />
            </div>
            {patch.status === "proposed" && (
              <div className="mt-2 flex flex-wrap gap-2">
                <button type="button" className="btn-primary px-3 py-1.5 text-xs" onClick={() => onApprove(patch.patch_id)}>
                  Approve
                </button>
                <button type="button" className="btn-secondary px-3 py-1.5 text-xs" onClick={() => onReject(patch.patch_id)}>
                  Reject
                </button>
                <Link to={`/p/${projectId}/fix`} className="btn-secondary px-3 py-1.5 text-xs">
                  Edit on Fix page
                </Link>
              </div>
            )}
          </div>
        ))}

        {saved && msg.content && (
          <div className="-ml-2 flex items-center gap-0.5" aria-label="Reply actions">
            <button type="button" onClick={() => void copy()} className={actionClass} title="Copy reply" aria-label="Copy reply">
              {copied ? <CheckIcon className="h-4 w-4 text-fixed" /> : <CopyIcon />}
            </button>
            {canRegenerate && (
              <button type="button" onClick={onRegenerate} className={actionClass} title="Regenerate" aria-label="Regenerate reply">
                <RefreshIcon />
              </button>
            )}
            <button
              type="button"
              onClick={() => onFeedback(msg.feedback === 1 ? 0 : 1)}
              className={`${actionClass} ${msg.feedback === 1 ? "bg-ink text-cream hover:bg-ink" : ""}`}
              title="Helpful"
              aria-label="Mark reply helpful"
              aria-pressed={msg.feedback === 1}
            >
              <ThumbUpIcon />
            </button>
            <button
              type="button"
              onClick={() => onFeedback(msg.feedback === -1 ? 0 : -1)}
              className={`${actionClass} ${msg.feedback === -1 ? "bg-ink text-cream hover:bg-ink" : ""}`}
              title="Not helpful"
              aria-label="Mark reply not helpful"
              aria-pressed={msg.feedback === -1}
            >
              <ThumbDownIcon />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export function ThinkingDots() {
  return (
    <span className="inline-flex items-center gap-1 py-2" aria-label="FixPilot is thinking">
      {[0, 1, 2].map((dot) => (
        <span
          key={dot}
          className="h-2 w-2 animate-bounce rounded-full bg-ink"
          style={{ animationDelay: `${dot * 0.15}s` }}
        />
      ))}
    </span>
  );
}

function Markdown({ body }: { body: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        code({ className, children, ...props }) {
          const match = /language-(\w+)/.exec(className || "");
          const code = String(children).replace(/\n$/, "");
          if (match) {
            return (
              <div className="relative my-2 overflow-hidden rounded-xl border border-line">
                <button
                  type="button"
                  className="absolute right-2 top-2 z-10 rounded-lg border border-line bg-panel px-2 py-0.5 text-[11px] text-ink"
                  onClick={() => void navigator.clipboard.writeText(code)}
                >
                  Copy
                </button>
                <SyntaxHighlighter style={oneLight} language={match[1]} PreTag="div">
                  {code}
                </SyntaxHighlighter>
              </div>
            );
          }
          return (
            <code className="rounded bg-panel px-1 font-mono text-[0.85em]" {...props}>
              {children}
            </code>
          );
        },
        a({ href, children }) {
          return (
            <a href={href} className="underline" target="_blank" rel="noreferrer">
              {children}
            </a>
          );
        },
        ul({ children }) {
          return <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>;
        },
        ol({ children }) {
          return <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>;
        },
        p({ children }) {
          return <p className="my-2 first:mt-0 last:mb-0">{children}</p>;
        },
      }}
    >
      {body}
    </ReactMarkdown>
  );
}
