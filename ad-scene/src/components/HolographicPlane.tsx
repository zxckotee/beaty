import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { holographicFragment, holographicVertex } from "../shaders/holographic";

const MOOD_TINTS: Record<string, [string, string, string]> = {
  hook: ["#7b5cff", "#22d3ff", "#ff6bcb"],
  maps: ["#3d8bff", "#2ef2ff", "#9b6dff"],
  fork: ["#ff4d6d", "#22d3ff", "#8b5cf6"],
  pain: ["#ff2e63", "#ff6b35", "#5c1a2e"],
  solution: ["#00e676", "#22d3ff", "#b388ff"],
  cta: ["#ffd54f", "#22d3ff", "#e040fb"],
};

type Props = {
  width: number;
  height: number;
  mood: keyof typeof MOOD_TINTS;
  tilt: number;
};

export function HolographicPlane({ width, height, mood, tilt }: Props) {
  const groupRef = useRef<THREE.Group>(null);
  const meshRef = useRef<THREE.Mesh>(null);
  const [a, b, c] = MOOD_TINTS[mood] ?? MOOD_TINTS.hook;

  const geometry = useMemo(
    () => new THREE.PlaneGeometry(width, height, 64, 48),
    [width, height],
  );

  const material = useMemo(() => {
    return new THREE.ShaderMaterial({
      vertexShader: holographicVertex,
      fragmentShader: holographicFragment,
      transparent: true,
      uniforms: {
        uTime: { value: 0 },
        uRipple: { value: mood === "pain" ? 0.6 : 1.2 },
        uDisplacement: { value: 0 },
        uTintA: { value: new THREE.Color(a) },
        uTintB: { value: new THREE.Color(b) },
        uTintC: { value: new THREE.Color(c) },
        uGlow: { value: mood === "cta" ? 1.2 : 0.75 },
      },
    });
  }, [a, b, c, mood]);

  useFrame((state) => {
    if (material.uniforms.uTime) {
      material.uniforms.uTime.value = state.clock.elapsedTime;
    }
    if (groupRef.current) {
      groupRef.current.rotation.x = tilt * 0.35 + Math.sin(state.clock.elapsedTime * 0.4) * 0.06;
      groupRef.current.rotation.y = Math.sin(state.clock.elapsedTime * 0.25) * 0.12;
    }
  });

  return (
    <group ref={groupRef}>
      <mesh ref={meshRef} geometry={geometry} material={material} receiveShadow castShadow />
    </group>
  );
}