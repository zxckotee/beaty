import { useMemo, useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import { RoundedBox, Text } from "@react-three/drei";
import type { Group } from "three";
import * as THREE from "three";
import type { WidgetDef } from "../story";
import { layoutAtTime, widgetEmphasis } from "../timeline";
import { UI } from "../uiTokens";
import type { PlaybackState } from "../playback";
import type { MutableRefObject } from "react";

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
  playbackRef: MutableRefObject<PlaybackState>;
  onClick: (index: number) => void;
};

export function UiWidget3d({ index, def, playbackRef, onClick }: Props) {
  const ref = useRef<Group>(null);
  const [hovered, setHovered] = useState(false);
  const { bg, text, emissive, emissiveInt } = colorsFor(def.kind);

  const zAnim = useRef(0.02);
  const scaleAnim = useRef(1);
  const xAnim = useRef(def.x);
  const yAnim = useRef(def.y);

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

  useFrame((_, delta) => {
    const pb = playbackRef.current;
    const layout = layoutAtTime(pb.timeMs)[index];
    const emphasis = widgetEmphasis(index, pb.timeMs, pb.popped);
    const hoverBoost = hovered ? 0.08 : 0;
    const targetZ = 0.02 + emphasis * 0.4 + hoverBoost;
    const targetScale = 1 + emphasis * 0.05;

    const k = 1 - Math.exp(-14 * delta);
    zAnim.current += (targetZ - zAnim.current) * k;
    scaleAnim.current += (targetScale - scaleAnim.current) * k;
    xAnim.current += (layout.x - xAnim.current) * k;
    yAnim.current += (layout.y - yAnim.current) * k;

    material.emissiveIntensity = emissiveInt + emphasis * 0.35 + (hovered ? 0.1 : 0);

    if (ref.current) {
      ref.current.position.set(xAnim.current, yAnim.current, zAnim.current);
      ref.current.scale.setScalar(scaleAnim.current);
      ref.current.renderOrder = emphasis > 0.55 ? 8 : 0;
    }
  });

  return (
    <group
      ref={ref}
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
    </group>
  );
}