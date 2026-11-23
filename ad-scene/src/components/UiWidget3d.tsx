import { useMemo, useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import { RoundedBox, Text } from "@react-three/drei";
import { a, useSpring } from "@react-spring/three";
import type { Group } from "three";
import * as THREE from "three";
import type { WidgetDef } from "../story";
import { UI } from "../uiTokens";

function colorsFor(kind: WidgetDef["kind"]) {
  switch (kind) {
    case "primary":
      return { bg: UI.gold, text: UI.accentInk, emissive: UI.goldDeep, emissiveInt: 0.15 };
    case "ghost":
      return { bg: UI.surface2, text: UI.muted, emissive: "#000000", emissiveInt: 0 };
    case "chip-warn":
      return { bg: "#3a2b12", text: UI.warn, emissive: UI.warn, emissiveInt: 0.2 };
    case "chip-bad":
      return { bg: "#3b1822", text: UI.bad, emissive: UI.bad, emissiveInt: 0.2 };
    case "soft":
      return { bg: UI.surface2, text: UI.gold, emissive: UI.gold, emissiveInt: 0.08 };
    default:
      return { bg: UI.surface, text: UI.text, emissive: "#000000", emissiveInt: 0 };
  }
}

type Props = {
  index: number;
  def: WidgetDef;
  active: boolean;
  pop: boolean;
  onClick: (index: number) => void;
};

export function UiWidget3d({ index, def, active, pop, onClick }: Props) {
  const ref = useRef<Group>(null);
  const [hovered, setHovered] = useState(false);
  const { bg, text, emissive, emissiveInt } = colorsFor(def.kind);

  const lift = pop ? 0.42 : active ? 0.22 : hovered ? 0.12 : 0.02;
  const scale = pop ? 1.06 : active ? 1.03 : 1;

  const spring = useSpring({
    z: lift,
    scale,
    config: pop ? { tension: 280, friction: 16 } : { tension: 200, friction: 22 },
  });

  useFrame(() => {
    if (!ref.current) return;
    ref.current.renderOrder = pop ? 10 : active ? 5 : 0;
  });

  const material = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: bg,
        emissive: new THREE.Color(emissive),
        emissiveIntensity: emissiveInt,
        metalness: def.kind === "primary" ? 0.35 : 0.05,
        roughness: def.kind === "primary" ? 0.45 : 0.9,
      }),
    [bg, def.kind, emissive, emissiveInt],
  );

  material.emissiveIntensity = pop ? emissiveInt + 0.35 : active ? emissiveInt + 0.2 : emissiveInt;

  return (
    <a.group
      ref={ref}
      position-x={def.x}
      position-y={def.y}
      position-z={spring.z}
      scale={spring.scale}
      onClick={(e) => {
        e.stopPropagation();
        onClick(index);
      }}
      onPointerOver={() => setHovered(true)}
      onPointerOut={() => setHovered(false)}
    >
      <RoundedBox
        args={[def.w, def.h, 0.08]}
        radius={def.kind.includes("chip") ? 0.2 : UI.radiusSm}
        smoothness={3}
        material={material}
        castShadow
        receiveShadow
      />
      <Text
        position={[0, def.h * 0.14, 0.05]}
        fontSize={Math.min(def.w, def.h) * 0.2}
        color={text}
        anchorX="center"
        anchorY="middle"
        maxWidth={def.w * 0.9}
        fontWeight={def.kind === "primary" ? 700 : 600}
      >
        {def.title}
      </Text>
      <Text
        position={[0, -def.h * 0.16, 0.05]}
        fontSize={Math.min(def.w, def.h) * 0.13}
        color={UI.muted}
        anchorX="center"
        anchorY="middle"
        maxWidth={def.w * 0.92}
      >
        {def.line}
      </Text>
    </a.group>
  );
}