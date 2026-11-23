export const holographicVertex = /* glsl */ `
uniform float uTime;
uniform float uRipple;
uniform float uDisplacement;

varying vec2 vUv;
varying vec3 vWorldNormal;
varying float vWave;

void main() {
  vUv = uv;
  vec3 pos = position;

  float w1 = sin(pos.x * 12.0 + uTime * 1.8) * 0.12;
  float w2 = sin(pos.y * 10.0 + uTime * 1.4) * 0.1;
  float w3 = sin((pos.x + pos.y) * 8.0 + uTime * 2.2) * 0.06;
  float wave = (w1 + w2 + w3) * uRipple;
  vWave = wave;
  pos.z += wave + uDisplacement;

  vec4 mv = modelViewMatrix * vec4(pos, 1.0);
  vWorldNormal = normalize(normalMatrix * normal);
  gl_Position = projectionMatrix * mv;
}
`;

export const holographicFragment = /* glsl */ `
uniform float uTime;
uniform vec3 uTintA;
uniform vec3 uTintB;
uniform vec3 uTintC;
uniform float uGlow;

varying vec2 vUv;
varying vec3 vWorldNormal;
varying float vWave;

void main() {
  float fresnel = pow(1.0 - abs(dot(normalize(vWorldNormal), vec3(0.0, 0.0, 1.0))), 1.8);

  float iridescent = sin(vUv.x * 28.0 + uTime * 2.0) * 0.5
    + sin(vUv.y * 22.0 - uTime * 1.6) * 0.5
    + sin((vUv.x + vUv.y) * 18.0 + uTime * 3.0) * 0.35;

  vec3 base = mix(uTintA, uTintB, vUv.x + iridescent * 0.25);
  base = mix(base, uTintC, vUv.y * 0.6 + fresnel * 0.4);

  vec3 holo = base + vec3(0.35, 0.2, 0.55) * fresnel;
  holo += vec3(0.15, 0.35, 0.5) * sin(uTime * 4.0 + vUv.x * 40.0) * 0.15;
  holo += vec3(uGlow * 0.25) * (0.5 + vWave * 2.0);

  gl_FragColor = vec4(holo, 0.92);
}
`;