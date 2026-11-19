import { ContactShadows, Float, Html, RoundedBox } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import {
  Color,
  type Group,
  type Mesh,
  type MeshStandardMaterial,
} from "three";

const CYCLE = 8;
const MAX_TILT = (10 * Math.PI) / 180;
const BUG = new Color("#C0392B");
const FIXED = new Color("#1E8449");
const LINE_COUNT = 5;

function CodeBlockHero() {
  const root = useRef<Group>(null);
  const floatY = useRef(0);
  const lineMats = useRef<(MeshStandardMaterial | null)[]>([]);
  const shield = useRef<Group>(null);
  const scratch = useMemo(() => new Color(), []);

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
      const mat = lineMats.current[i];
      if (!mat) continue;
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
      shield.current.scale.setScalar(0.55 + rise * 0.55);
      shield.current.rotation.y = rise * Math.PI * 0.35;
      shield.current.visible = rise > 0.02;
    }
  });

  const lineWidths = [1.7, 1.35, 1.9, 1.1, 1.55];

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

      {lineWidths.map((width, index) => (
        <mesh
          key={index}
          position={[-1.05 + width / 2, 0.62 - index * 0.24, 0.16]}
          ref={(node: Mesh | null) => {
            if (node) lineMats.current[index] = node.material as MeshStandardMaterial;
          }}
        >
          <boxGeometry args={[width, 0.07, 0.02]} />
          <meshStandardMaterial
            color="#C0392B"
            emissive="#C0392B"
            emissiveIntensity={0.5}
            metalness={0.05}
            roughness={0.4}
          />
        </mesh>
      ))}

      {/* Rising shield + check */}
      <group ref={shield} position={[0, -0.15, 0.35]} visible={false}>
        <mesh>
          <cylinderGeometry args={[0.42, 0.5, 0.12, 6]} />
          <meshStandardMaterial color="#111111" metalness={0.4} roughness={0.32} />
        </mesh>
        <mesh position={[0, 0, 0.07]}>
          <cylinderGeometry args={[0.3, 0.36, 0.05, 6]} />
          <meshStandardMaterial color="#F5F0E6" metalness={0.05} roughness={0.55} />
        </mesh>
        <RoundedBox args={[0.28, 0.07, 0.05]} radius={0.02} position={[0.02, -0.02, 0.12]} rotation={[0, 0, -0.55]}>
          <meshStandardMaterial color="#1E8449" metalness={0.2} roughness={0.35} />
        </RoundedBox>
        <RoundedBox args={[0.12, 0.07, 0.05]} radius={0.02} position={[-0.1, -0.06, 0.12]} rotation={[0, 0, 0.7]}>
          <meshStandardMaterial color="#1E8449" metalness={0.2} roughness={0.35} />
        </RoundedBox>
      </group>
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
      <OrbitTag label="Detect" phase={0} radius={2.15} speed={0.35} />
      <OrbitTag label="Repair" phase={(Math.PI * 2) / 3} radius={2.15} speed={0.35} />
      <OrbitTag label="Verify" phase={(Math.PI * 4) / 3} radius={2.15} speed={0.35} />
      <ContactShadows
        position={[0, -1.15, 0]}
        opacity={0.35}
        scale={8}
        blur={2.4}
        far={3.5}
        color="#111111"
        frames={1}
      />
      {/* Soft cream floor plane (receives visual weight) */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -1.16, 0]}>
        <circleGeometry args={[3.2, 48]} />
        <meshStandardMaterial color="#F5F0E6" roughness={0.95} metalness={0} />
      </mesh>
    </>
  );
}

export default function HeroShieldScene() {
  return (
    <Canvas
      camera={{ position: [0, 0.55, 5.2], fov: 38 }}
      dpr={[1, 1.5]}
      gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      style={{ touchAction: "none" }}
    >
      <SceneContents />
    </Canvas>
  );
}
