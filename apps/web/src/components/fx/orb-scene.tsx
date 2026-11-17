"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import * as THREE from "three";

export type OrbMood = "idle" | "listening" | "thinking" | "speaking" | "muted" | "connecting";

// 3D simplex noise (Ashima Arts / Stefan Gustavson, MIT).
const NOISE = /* glsl */ `
vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+10.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1.0/6.0,1.0/3.0);
  const vec4 D=vec4(0.0,0.5,1.0,2.0);
  vec3 i=floor(v+dot(v,C.yyy));
  vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz);
  vec3 l=1.0-g;
  vec3 i1=min(g.xyz,l.zxy);
  vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx;
  vec3 x2=x0-i2+C.yyy;
  vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
  float n_=0.142857142857;
  vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.0*floor(p*ns.z*ns.z);
  vec4 x_=floor(j*ns.z);
  vec4 y_=floor(j-7.0*x_);
  vec4 x=x_*ns.x+ns.yyyy;
  vec4 y=y_*ns.x+ns.yyyy;
  vec4 h=1.0-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy);
  vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.0+1.0;
  vec4 s1=floor(b1)*2.0+1.0;
  vec4 sh=-step(h,vec4(0.0));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy;
  vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x);
  vec3 p1=vec3(a0.zw,h.y);
  vec3 p2=vec3(a1.xy,h.z);
  vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x;p1*=norm.y;p2*=norm.z;p3*=norm.w;
  vec4 m=max(0.5-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0);
  m=m*m;
  return 105.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}`;

const VERTEX = /* glsl */ `
uniform float uTime;
uniform float uAmp;
uniform float uFreq;
varying vec3 vNormal;
varying vec3 vView;
varying vec3 vObjNormal;
varying float vNoise;
${NOISE}
float field(vec3 dir) {
  vec3 t = vec3(uTime * 0.31, uTime * 0.23, uTime * 0.19);
  return snoise(dir * uFreq + t) + 0.18 * snoise(dir * uFreq * 2.4 - t * 1.6);
}
vec3 displace(vec3 dir) {
  return dir * (1.0 + field(dir) * uAmp);
}
void main() {
  vec3 dir = normalize(position);
  vNoise = field(dir);
  vec3 p = dir * (1.0 + vNoise * uAmp);
  // Recompute the normal of the displaced surface from two nearby samples (smooth lighting).
  vec3 up = abs(dir.y) > 0.99 ? vec3(1.0, 0.0, 0.0) : vec3(0.0, 1.0, 0.0);
  vec3 tangent = normalize(cross(up, dir));
  vec3 bitangent = normalize(cross(dir, tangent));
  float e = 0.012;
  vec3 pt = displace(normalize(dir + tangent * e));
  vec3 pb = displace(normalize(dir + bitangent * e));
  vec3 n = normalize(cross(pt - p, pb - p));
  if (dot(n, dir) < 0.0) n = -n;
  vObjNormal = n;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  vNormal = normalize(normalMatrix * n);
  vView = normalize(-mv.xyz);
  gl_Position = projectionMatrix * mv;
}`;

const FRAGMENT = /* glsl */ `
uniform vec3 uC1;
uniform vec3 uC2;
uniform vec3 uC3;
uniform float uGlow;
uniform float uTime;
varying vec3 vNormal;
varying vec3 vView;
varying vec3 vObjNormal;
varying float vNoise;
void main() {
  vec3 n = normalize(vNormal);
  vec3 L = normalize(vec3(-0.45, 0.75, 0.65));
  float diff = max(dot(n, L), 0.0);
  vec3 H = normalize(L + vView);
  float spec = pow(max(dot(n, H), 0.0), 60.0);
  float fres = pow(1.0 - max(dot(vView, n), 0.0), 2.6);
  // Iridescent body: two colours flow with the noise, the third sweeps around the orb.
  float t = smoothstep(-0.9, 0.9, vNoise);
  vec3 body = mix(uC1, uC2, t);
  float sweep = 0.5 + 0.5 * sin(vObjNormal.y * 2.2 + vObjNormal.x * 1.4 + uTime * 0.9);
  body = mix(body, uC3, sweep * 0.45);
  vec3 col = body * (0.32 + 0.78 * diff);
  col += spec * vec3(1.0) * 0.65;
  col += fres * mix(uC2, uC3, 0.5) * 1.1 * uGlow;
  gl_FragColor = vec4(col, 1.0);
  #include <colorspace_fragment>
}`;

const MOODS: Record<OrbMood, { amp: number; speed: number; glow: number; spin: number }> = {
  idle: { amp: 0.085, speed: 0.45, glow: 1.0, spin: 0.12 },
  connecting: { amp: 0.14, speed: 1.4, glow: 1.1, spin: 0.6 },
  listening: { amp: 0.17, speed: 0.9, glow: 1.25, spin: 0.2 },
  thinking: { amp: 0.2, speed: 1.8, glow: 1.35, spin: 0.9 },
  speaking: { amp: 0.16, speed: 1.2, glow: 1.4, spin: 0.3 },
  muted: { amp: 0.05, speed: 0.3, glow: 0.7, spin: 0.05 },
};

function hasWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    const gl = canvas.getContext("webgl2") ?? canvas.getContext("webgl");
    gl?.getExtension("WEBGL_lose_context")?.loseContext();
    return gl !== null;
  } catch {
    return false;
  }
}

/**
 * The orb as a plain three.js scene: one displaced icosphere with a custom shader. Animation runs on
 * `renderer.setAnimationLoop` with `THREE.Timer`, pauses while the orb is off screen, and releases
 * the WebGL context on unmount. Props are read through a ref so they never restart the scene.
 */
export default function OrbScene({
  mood,
  level = 0,
  colors,
  fallback,
}: {
  mood: OrbMood;
  level?: number;
  colors: [string, string, string];
  fallback: ReactNode;
}) {
  const host = useRef<HTMLDivElement>(null);
  const live = useRef({ mood, level, colors });
  // Only rendered in the browser (Orb3D loads this module with ssr: false), so probing here is safe.
  const [webgl] = useState(hasWebGL);

  useEffect(() => {
    live.current = { mood, level, colors };
  }, [mood, level, colors]);

  useEffect(() => {
    const el = host.current;
    if (!webgl || !el) return;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: "high-performance" });
    } catch {
      return; // Context creation failed after the probe; leave the spot empty rather than crash.
    }
    renderer.setClearColor(0x000000, 0);
    const canvas = renderer.domElement;
    canvas.style.display = "block";
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    el.appendChild(canvas);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100);
    camera.position.set(0, 0, 3.7);

    const start = live.current.colors;
    const uniforms = {
      uTime: { value: 0 },
      uAmp: { value: 0.13 },
      uFreq: { value: 0.95 },
      uGlow: { value: 1 },
      uC1: { value: new THREE.Color(start[0]) },
      uC2: { value: new THREE.Color(start[1]) },
      uC3: { value: new THREE.Color(start[2]) },
    };
    const geometry = new THREE.IcosahedronGeometry(1, 40);
    const material = new THREE.ShaderMaterial({
      uniforms,
      vertexShader: VERTEX,
      fragmentShader: FRAGMENT,
      toneMapped: false,
    });
    const mesh = new THREE.Mesh(geometry, material);
    scene.add(mesh);

    const resize = () => {
      const { width, height } = el.getBoundingClientRect();
      if (!width || !height) return;
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };
    resize();
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(el);

    let visible = true;
    const visibility = new IntersectionObserver(([entry]) => {
      visible = entry?.isIntersecting ?? true;
    });
    visibility.observe(el);

    // Parallax: the orb leans toward the pointer, measured from the orb's centre (-1..1, clamped).
    const pointer = new THREE.Vector2();
    const onPointerMove = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      pointer.set(
        THREE.MathUtils.clamp(((e.clientX - r.left) / r.width) * 2 - 1, -1, 1),
        THREE.MathUtils.clamp(1 - ((e.clientY - r.top) / r.height) * 2, -1, 1),
      );
    };
    window.addEventListener("pointermove", onPointerMove, { passive: true });

    const timer = new THREE.Timer();
    timer.connect(document); // Avoids a huge first delta after the tab was hidden.
    const targets = [new THREE.Color(), new THREE.Color(), new THREE.Color()];
    const parsed = ["", "", ""];
    let elapsed = 0;

    renderer.setAnimationLoop((time) => {
      timer.update(time);
      if (!visible) return;
      const d = Math.min(timer.getDelta(), 0.05);
      const now = live.current;
      for (let i = 0; i < 3; i++) {
        if (parsed[i] !== now.colors[i]) {
          targets[i].set(now.colors[i]);
          parsed[i] = now.colors[i];
        }
      }
      const target = MOODS[now.mood];
      elapsed += d * target.speed;
      uniforms.uTime.value = elapsed;
      const amp = target.amp + (now.mood === "speaking" ? Math.min(now.level, 1) * 0.25 : 0);
      uniforms.uAmp.value += (amp - uniforms.uAmp.value) * Math.min(1, d * 6);
      uniforms.uGlow.value += (target.glow - uniforms.uGlow.value) * Math.min(1, d * 4);
      uniforms.uC1.value.lerp(targets[0], d * 2);
      uniforms.uC2.value.lerp(targets[1], d * 2);
      uniforms.uC3.value.lerp(targets[2], d * 2);
      mesh.rotation.y += d * target.spin;
      mesh.rotation.x += (pointer.y * 0.35 - mesh.rotation.x) * d * 2;
      mesh.rotation.z += (-pointer.x * 0.25 - mesh.rotation.z) * d * 2;
      renderer.render(scene, camera);
    });

    return () => {
      renderer.setAnimationLoop(null);
      resizeObserver.disconnect();
      visibility.disconnect();
      window.removeEventListener("pointermove", onPointerMove);
      timer.dispose();
      geometry.dispose();
      material.dispose();
      renderer.dispose();
      renderer.forceContextLoss(); // Free the GPU context now; browsers cap how many can be live.
      canvas.remove();
    };
  }, [webgl]);

  if (!webgl) return <div className="grid size-full place-items-center">{fallback}</div>;
  return <div ref={host} aria-hidden className="size-full" />;
}
