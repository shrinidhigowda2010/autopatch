import { Suspense, lazy, useEffect, useState } from "react";

const Scene = lazy(() => import("./HeroShieldScene"));

function HeroFallback() {
  return (
    <div className="flex h-full w-full items-center justify-center" aria-hidden>
      <svg viewBox="0 0 320 240" className="h-56 w-auto max-w-full md:h-72" role="img" aria-label="Code repair illustration">
        <ellipse cx="160" cy="210" rx="110" ry="12" fill="#111111" opacity="0.08" />
        <rect x="60" y="48" width="200" height="130" rx="16" fill="#111111" />
        <rect x="74" y="62" width="172" height="102" rx="10" fill="#1a1a1a" />
        <rect x="88" y="78" width="120" height="8" rx="3" fill="#C0392B" />
        <rect x="88" y="98" width="95" height="8" rx="3" fill="#1E8449" />
        <rect x="88" y="118" width="140" height="8" rx="3" fill="#1E8449" />
        <rect x="88" y="138" width="70" height="8" rx="3" fill="#1E8449" />
        <path
          d="M160 28c0 0 22 5 22 5v28c0 16-11 29-22 34-11-5-22-18-22-34V33s22-5 22-5z"
          fill="#111111"
        />
        <path
          d="M152 48l8 8 16-18"
          fill="none"
          stroke="#F5F0E6"
          strokeWidth="4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <g fontFamily="ui-sans-serif, system-ui" fontSize="11" fontWeight="600" fill="#111111">
          <rect x="28" y="20" width="52" height="22" rx="11" fill="#FBF8F2" stroke="#E4DCCB" />
          <text x="54" y="35" textAnchor="middle">
            Detect
          </text>
          <rect x="236" y="36" width="52" height="22" rx="11" fill="#FBF8F2" stroke="#E4DCCB" />
          <text x="262" y="51" textAnchor="middle">
            Repair
          </text>
          <rect x="248" y="168" width="52" height="22" rx="11" fill="#FBF8F2" stroke="#E4DCCB" />
          <text x="274" y="183" textAnchor="middle">
            Verify
          </text>
        </g>
      </svg>
    </div>
  );
}

export default function HeroShield() {
  const [allow3d, setAllow3d] = useState(false);

  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const cores = navigator.hardwareConcurrency || 2;
    const slow =
      cores <= 2 || (navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData;
    setAllow3d(!reduced && !slow);
  }, []);

  if (!allow3d) {
    return (
      <div className="h-64 w-full md:h-80">
        <HeroFallback />
      </div>
    );
  }

  return (
    <div className="h-64 w-full md:h-80 lg:h-[22rem]">
      <Suspense
        fallback={
          <div className="h-full w-full">
            <HeroFallback />
          </div>
        }
      >
        <Scene />
      </Suspense>
    </div>
  );
}
