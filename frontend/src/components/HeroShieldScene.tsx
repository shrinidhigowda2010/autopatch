import { ContactShadows, Float, Html, RoundedBox } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Color,
  ExtrudeGeometry,
  Shape,
  type Group,
  MeshStandardMaterial,
} from "three";

const CYCLE = 8;
const MAX_TILT = (10 * Math.PI) / 180;
const BUG = new Color("#C0392B");
const FIXED = new Color("#1E8449");

// Each code line is a few "tokens" (indent, keyword, rest) so it reads as code, not bars.
const CODE_LINES: { indent: number; tokens: number[] }[] = [
  { indent: 0, tokens: [0.32, 0.62, 0.3] },
  { indent: 0.18, tokens: [0.22, 0.48, 0.5] },
  { indent: 0.36, tokens: [0.4, 0.28, 0.66] },
  { indent: 0.18, tokens: [0.3, 0.4] },
  { indent: 0, tokens: [0.26, 0.7, 0.24] },
];
const LINE_COUNT = CODE_LINES.length;
const TOKEN_GAP = 0.07;

/** A classic shield outline, extruded with a soft bevel. */
function useShieldGeometry() {
  return useMemo(() => {
    const shape = new Shape();
    shape.moveTo(0, 0.62);
    shape.bezierCurveTo(0.2, 0.5, 0.4, 0.48, 0.5, 0.48);
    shape.lineTo(0.5, 0.05);
    shape.bezierCurveTo(0.5, -0.32, 0.22, -0.52, 0, -0.64);
    shape.bezierCurveTo(-0.22, -0.52, -0.5, -0.32, -0.5, 0.05);
    shape.lineTo(-0.5, 0.48);
    shape.bezierCurveTo(-0.4, 0.48, -0.2, 0.5, 0, 0.62);
    const geometry = new ExtrudeGeometry(shape, {
      depth: 0.12,
      bevelEnabled: true,
      bevelThickness: 0.04,
      bevelSize: 0.035,
      bevelSegments: 4,
      curveSegments: 24,
    });
    geometry.center();
    return geometry;
  }, []);
}

/** The check mark as a thick extruded stroke. */
function useCheckGeometry() {
  return useMemo(() => {
    const w = 0.065;
    const shape = new Shape();
    shape.moveTo(-0.24, 0.02);
    shape.lineTo(-0.07, -0.15);
    shape.lineTo(0.25, 0.2);
    shape.lineTo(0.25 - w, 0.2 + w * 0.9);
    shape.lineTo(-0.07, -0.15 + w * 1.6);
    shape.lineTo(-0.24 + w * 0.8, 0.02 + w * 0.9);
    shape.closePath();
    const geometry = new ExtrudeGeometry(shape, { depth: 0.04, bevelEnabled: true, bevelThickness: 0.012, bevelSize: 0.012, bevelSegments: 2 });
    geometry.center();
    return geometry;
  }, []);
}

function CodeBlockHero() {
  const root = useRef<Group>(null);
  const floatY = useRef(0);
  const lineMats = useMemo(
    () =>
      CODE_LINES.map(
        () => new MeshStandardMaterial({ color: "#C0392B", emissive: "#C0392B", emissiveIntensity: 0.5, roughness: 0.4 }),
      ),
    [],
  );
  const shield = useRef<Group>(null);
  const scratch = useMemo(() => new Color(), []);
  const shieldGeometry = useShieldGeometry();
  const checkGeometry = useCheckGeometry();

  useFrame((state, delta) => {
    const t = state.clock.elapsedTime % CYCLE;
    const pointerX = state.pointer.x;
    const pointerY = state.pointer.y;

    // Gentle float
    floatY.current = Math.sin(state.clock.elapsedTime * 0.9) * 0.08;

    if (root.current) {
      const targetX = -pointerY * MAX_TILT;
      const targetY = pointerX * MAX_TILT;
      root.current.rotation.x += (targetX - root.current.rotation.x) * Math.min(1, delta * 6);
      root.current.rotation.y += (targetY - root.current.rotation.y) * Math.min(1, delta * 6);
      root.current.position.y = floatY.current;
    }

    // Lines: red → green one by one between 0.8s and 4.2s
    for (let i = 0; i < LINE_COUNT; i += 1) {
      const mat = lineMats[i];
      const start = 0.8 + i * 0.65;
      const local = Math.min(1, Math.max(0, (t - start) / 0.45));
      scratch.copy(BUG).lerp(FIXED, local);
      mat.color.copy(scratch);
      mat.emissive.copy(scratch);
      mat.emissiveIntensity = 0.45 + local * 0.35;
    }

    // Shield rises after lines are fixed
    if (shield.current) {
      let rise = 0;
      if (t >= 4.2 && t < 6.8) {
        const u = Math.min(1, (t - 4.2) / 0.9);
        const ease = 1 - Math.pow(1 - u, 3);
        rise = ease;
      } else if (t >= 6.8 && t < 7.4) {
        rise = 1;
      } else if (t >= 7.4) {
        rise = Math.max(0, 1 - (t - 7.4) / 0.55);
      }
      shield.current.position.y = -0.15 + rise * 1.35;
      shield.current.scale.setScalar(0.4 + rise * 0.45);
      shield.current.rotation.y = rise * Math.PI * 0.35;
      shield.current.visible = rise > 0.02;
    }
  });

  return (
    <group ref={root} position={[0, 0.15, 0]}>
      {/* Matte black code slab */}
      <RoundedBox args={[2.6, 1.7, 0.22]} radius={0.08} smoothness={4} position={[0, 0.15, 0]}>
        <meshStandardMaterial color="#111111" metalness={0.18} roughness={0.72} />
      </RoundedBox>
      {/* Cream bezel / screen inset */}
      <RoundedBox args={[2.35, 1.45, 0.06]} radius={0.05} smoothness={4} position={[0, 0.15, 0.12]}>
        <meshStandardMaterial color="#1a1a1a" metalness={0.1} roughness={0.55} />
      </RoundedBox>

      {CODE_LINES.map((line, index) => (
        <CodeLine
          key={index}
          line={line}
          y={0.62 - index * 0.24}
          material={lineMats[index]}
        />
      ))}

      {/* Rising shield + check */}
      <group ref={shield} position={[0, -0.15, 0.35]} visible={false}>
        <mesh geometry={shieldGeometry}>
          <meshStandardMaterial color="#111111" metalness={0.45} roughness={0.3} />
        </mesh>
        <mesh geometry={checkGeometry} position={[0, 0, 0.12]}>
          <meshStandardMaterial color="#1E8449" emissive="#1E8449" emissiveIntensity={0.8} roughness={0.35} />
        </mesh>
      </group>
    </group>
  );
}

/**
 * One line of code. All its tokens share one material so the whole line
 * turns from red to green together.
 */
function CodeLine({
  line,
  y,
  material,
}: {
  line: { indent: number; tokens: number[] };
  y: number;
  material: MeshStandardMaterial;
}) {
  let x = -1.02 + line.indent;
  const segments = line.tokens.map((width) => {
    const center = x + width / 2;
    x += width + TOKEN_GAP;
    return { width, center };
  });

  return (
    <group position={[0, y, 0.16]}>
      {segments.map((segment, index) => (
        <mesh key={index} position={[segment.center, 0, 0]} material={material}>
          <boxGeometry args={[segment.width, 0.07, 0.02]} />
        </mesh>
      ))}
    </group>
  );
}

function OrbitTag({
  label,
  phase,
  radius,
  speed,
}: {
  label: string;
  phase: number;
  radius: number;
  speed: number;
}) {
  const ref = useRef<Group>(null);
  useFrame(({ clock }) => {
    if (!ref.current) return;
    const a = clock.elapsedTime * speed + phase;
    ref.current.position.x = Math.cos(a) * radius;
    ref.current.position.z = Math.sin(a) * radius * 0.55;
    ref.current.position.y = 0.55 + Math.sin(a * 1.4) * 0.2;
  });
  return (
    <group ref={ref}>
      <Html center distanceFactor={7} style={{ pointerEvents: "none", userSelect: "none" }}>
        <span className="whitespace-nowrap rounded-full border border-[#E4DCCB] bg-[#FBF8F2] px-2.5 py-1 text-[10px] font-semibold tracking-wide text-[#111111] shadow-sm">
          {label}
        </span>
      </Html>
    </group>
  );
}

function SceneContents() {
  return (
    <>
      <ambientLight intensity={0.7} />
      <directionalLight position={[3.5, 5, 4]} intensity={1.15} castShadow />
      <directionalLight position={[-3, 2, -2]} intensity={0.35} color="#F5F0E6" />
      <spotLight position={[0, 6, 2]} intensity={0.55} angle={0.45} penumbra={0.6} />
      <Float speed={1.1} rotationIntensity={0.08} floatIntensity={0.15}>
        <CodeBlockHero />
      </Float>
      <OrbitTag label="Detect" phase={0} radius={1.75} speed={0.35} />
      <OrbitTag label="Repair" phase={(Math.PI * 2) / 3} radius={1.75} speed={0.35} />
      <OrbitTag label="Verify" phase={(Math.PI * 4) / 3} radius={1.75} speed={0.35} />
      <ContactShadows
        position={[0, -1.15, 0]}
        opacity={0.35}
        scale={8}
        blur={2.4}
        far={3.5}
        color="#111111"
        frames={1}
      />
    </>
  );
}

export default function HeroShieldScene() {
  const wrapper = useRef<HTMLDivElement>(null);
  const [onScreen, setOnScreen] = useState(true);

  // Stop rendering when the hero is scrolled out of view to save battery.
  useEffect(() => {
    const node = wrapper.current;
    if (!node || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(([entry]) => setOnScreen(entry.isIntersecting), { threshold: 0.05 });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={wrapper} className="h-full w-full">
      <Canvas
        camera={{ position: [0, 0.55, 5.2], fov: 38 }}
        dpr={[1, 1.5]}
        frameloop={onScreen ? "always" : "never"}
        gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      >
        <SceneContents />
      </Canvas>
    </div>
  );
}
