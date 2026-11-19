import { useEffect, useRef } from "react";

const COLORS = ["#111111", "#1E8449", "#C0392B", "#B9770E", "#3A3A3A", "#E4DCCB"];

type Piece = { x: number; y: number; vx: number; vy: number; size: number; color: string; spin: number; angle: number };

// A one-shot confetti burst drawn on a full-screen canvas. Skipped for reduced motion.
export default function Confetti({ fire }: { fire: number }) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!fire || !canvas.current) return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const element = canvas.current;
    const context = element.getContext("2d");
    if (!context) return;
    element.width = window.innerWidth;
    element.height = window.innerHeight;
    const pieces: Piece[] = Array.from({ length: 180 }, () => ({
      x: element.width / 2 + (Math.random() - 0.5) * 200,
      y: element.height * 0.35,
      vx: (Math.random() - 0.5) * 16,
      vy: -Math.random() * 14 - 4,
      size: 6 + Math.random() * 6,
      color: COLORS[Math.floor(Math.random() * COLORS.length)],
      spin: (Math.random() - 0.5) * 0.3,
      angle: Math.random() * Math.PI,
    }));
    let frame = 0;
    const started = performance.now();
    const draw = (now: number) => {
      context.clearRect(0, 0, element.width, element.height);
      for (const piece of pieces) {
        piece.vy += 0.35;
        piece.vx *= 0.99;
        piece.x += piece.vx;
        piece.y += piece.vy;
        piece.angle += piece.spin;
        context.save();
        context.translate(piece.x, piece.y);
        context.rotate(piece.angle);
        context.fillStyle = piece.color;
        context.fillRect(-piece.size / 2, -piece.size / 4, piece.size, piece.size / 2);
        context.restore();
      }
      if (now - started < 3500) frame = requestAnimationFrame(draw);
      else context.clearRect(0, 0, element.width, element.height);
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [fire]);

  return <canvas ref={canvas} className="pointer-events-none fixed inset-0 z-50" aria-hidden="true" />;
}
