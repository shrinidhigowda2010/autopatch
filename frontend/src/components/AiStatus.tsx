import { useEffect, useState } from "react";
import { api } from "../api";

export default function AiStatus() {
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    api<{ gemini_configured?: boolean; ai_engine?: string }>("/api/health")
      .then((body) => {
        if (body.ai_engine) setOnline(body.ai_engine === "online");
        else setOnline(Boolean(body.gemini_configured));
      })
      .catch(() => setOnline(null));
  }, []);

  const label = online === null ? "checking" : online ? "online" : "standby";
  const color = online === null ? "bg-mist" : online ? "bg-fixed" : "bg-review";

  return (
    <p className="flex items-center gap-2 text-sm text-mist">
      <span className={`inline-block h-2 w-2 rounded-full ${color}`} aria-hidden />
      AI engine: {label}
    </p>
  );
}
