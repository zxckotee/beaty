import { useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import { Text } from "@react-three/drei";
import { a, useSpring } from "@react-spring/three";
import type { Group } from "three";

type Props = {
  index: number;
  col: number;
  row: number;
  cols: number;
  rows: number;
  width: number;
  height: number;
  title: string;
  line: string;
  active: boolean;
  pop: boolean;
  accent: [number, number, number];
  onClick: (index: number) => void;
};

export function PopSegment({
  index,
  col,
  row,
  cols,
  rows,
  width,
  height,
  title,
  line,
  active,
  pop,
  accent,
  onClick,
}: Props) {
  const ref = useRef<Group>(null);
  const [hovered, setHovered] = useState(false);
  const cellW = width / cols;
  const cellH = height / rows;
  const x = -width / 2 + cellW * (col + 0.5);
  const y = height / 2 - cellH * (row + 0.5);

  const targetZ = pop ? 1.35 : active ? 0.55 : hovered ? 0.25 : 0.08;
  const targetScale = pop ? 1.12 : active ? 1.05 : 1;

  const spring = useSpring({
    z: targetZ,
    scale: targetScale,
    config: pop ? { tension: 180, friction: 12 } : { tension: 120, friction: 18 },
  });

  const stripOpacity = pop ? 0.75 : active ? 0.55 : hovered ? 0.4 : 0.2;

  useFrame((state) => {
    if (!ref.current) return;
    const wobble = pop ? Math.sin(state.clock.elapsedTime * 12) * 0.02 : 0;
    ref.current.rotation.z = wobble;
  });

  return (
    <a.group ref={ref} position-x={x} position-y={y} position-z={spring.z} scale={spring.scale}>
      <mesh
        onPointerOver={() => setHovered(true)}
        onPointerOut={() => setHovered(false)}
        onClick={(e) => {
          e.stopPropagation();
          onClick(index);
        }}
        castShadow
        receiveShadow
      >
        <boxGeometry args={[cellW * 0.88, cellH * 0.82, 0.14]} />
        <meshStandardMaterial
          color={active || pop ? `rgb(${accent.map((c) => Math.round(c * 255)).join(",")})` : "#1a1228"}
          emissive={active || pop ? `rgb(${accent.map((c) => Math.round(c * 180)).join(",")})` : "#000000"}
          emissiveIntensity={pop ? 1.4 : active ? 0.9 : hovered ? 0.35 : 0.1}
          metalness={0.85}
          roughness={0.25}
        />
      </mesh>
      <mesh position={[0, 0, 0.09]}>
        <planeGeometry args={[cellW * 0.82, cellH * 0.12]} />
        <meshBasicMaterial color={accent} transparent opacity={stripOpacity} />
      </mesh>
      <Text
        position={[0, cellH * 0.12, 0.1]}
        fontSize={Math.min(cellW, cellH) * 0.11}
        color="#ffffff"
        anchorX="center"
        anchorY="middle"
        maxWidth={cellW * 0.75}
      >
        {title}
      </Text>
      <Text
        position={[0, -cellH * 0.12, 0.1]}
        fontSize={Math.min(cellW, cellH) * 0.075}
        color="#d8c8ff"
        anchorX="center"
        anchorY="middle"
        maxWidth={cellW * 0.8}
      >
        {line}
      </Text>
    </a.group>
  );
}