"use client";

import React, { useRef, useMemo } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import {
  RoundedBox,
  Sphere,
  Text,
  ContactShadows,
  Environment,
  Sparkles,
  Torus
} from "@react-three/drei";
import * as THREE from "three";

export type AIAvatarState = "idle" | "thinking" | "speaking";
export type AIAvatarEmotion =
  | "neutral"
  | "happy"
  | "excited"
  | "sad"
  | "confused"
  | "surprised"
  | "love"
  | "annoyed"
  | "angry"
  | "sleepy";

type Props = {
  state?: AIAvatarState;
  emotion?: AIAvatarEmotion;
  size?: number;
  className?: string;
};

// رنگ‌های مربوط به هر احساس
const emotionScreenColor: Record<AIAvatarEmotion, { glow: string; face: string; accent: string }> = {
  neutral: { glow: "#ffffff", face: "#ffffff", accent: "#aaaaaa" },
  happy: { glow: "#fcd34d", face: "#fcd34d", accent: "#f59e0b" },
  excited: { glow: "#f9a8d4", face: "#f9a8d4", accent: "#ec4899" },
  sad: { glow: "#93c5fd", face: "#93c5fd", accent: "#60a5fa" },
  confused: { glow: "#c4b5fd", face: "#c4b5fd", accent: "#a78bfa" },
  surprised: { glow: "#6ee7b7", face: "#6ee7b7", accent: "#34d399" },
  love: { glow: "#fda4af", face: "#fda4af", accent: "#f43f5e" },
  annoyed: { glow: "#fdba74", face: "#fdba74", accent: "#fb923c" },
  angry: { glow: "#fca5a5", face: "#fca5a5", accent: "#ef4444" },
  sleepy: { glow: "#a5b4fc", face: "#a5b4fc", accent: "#818cf8" },
};

export function AIAvatar({ state = "idle", emotion = "neutral", size = 300, className = "" }: Props) {
  return (
    <div
      className={`relative flex items-center justify-center select-none ${className}`}
      // اندکی بزرگ‌تر کردن قاب ظاهری برای نفس کشیدن فریم Canvas
      style={{ width: size, height: size * 1.15 }}
      aria-label={`AI is ${state}, feeling ${emotion}`}
    >
      <Canvas 
         // دور کردن جزئیِ دوربین به Z=5.8 تا مشکل بریدگی کامل رفع شود
         camera={{ position: [0, 0, 5.8], fov: 45 }}
         style={{ overflow: "visible" }}
      >
        <ambientLight intensity={0.6} />
        <directionalLight position={[5, 10, 5]} intensity={1.5} castShadow />
        <Environment preset="city" />

        {/* پایین کشیدن کلی مدل تا 0.15 تا به ذرات فضای اوج گیری بدهد */}
        <group position={[0, -0.15, 0]}>
          <Robot state={state} emotion={emotion} />
          {/* سایه که بر اساس فاصله تنظیم شده */}
          <ContactShadows position={[0, -1.7, 0]} opacity={0.6} scale={10} blur={2.5} far={4} />
        </group>

      </Canvas>
    </div>
  );
}

// ── مدل ربات ──────────────────────────────────────────────
function Robot({ state, emotion }: { state: AIAvatarState; emotion: AIAvatarEmotion }) {
  const groupRef = useRef<THREE.Group>(null);
  const leftArmRef = useRef<THREE.Mesh>(null);
  const rightArmRef = useRef<THREE.Mesh>(null);
  const colors = emotionScreenColor[emotion];

  // منطق حرکتی پیشرفته بدن
  useFrame((rootState) => {
    const t = rootState.clock.getElapsedTime();
    const isSpeaking = state === "speaking";
    const isSleepy = emotion === "sleepy";
    const isSad = emotion === "sad";
    const isConfused = emotion === "confused";
    const isAngry = emotion === "angry";
    const isExcited = emotion === "excited";

    if (groupRef.current) {
      const floatSpeed = isSleepy || isSad ? 1 : isExcited ? 5 : isSpeaking ? 3 : 2;
      const floatHeight = isSleepy || isSad ? 0.05 : isExcited ? 0.15 : 0.08;
      let targetY = Math.sin(t * floatSpeed) * floatHeight;

      if (isAngry) {
        targetY += (Math.random() - 0.5) * 0.04;
        groupRef.current.position.x = (Math.random() - 0.5) * 0.04;
      } else {
        groupRef.current.position.x = THREE.MathUtils.lerp(groupRef.current.position.x, 0, 0.1);
      }
      groupRef.current.position.y = targetY;

      let targetRotX = 0;
      let targetRotY = 0;
      let targetRotZ = 0;

      if (!isSleepy) {
        targetRotY = (rootState.pointer.x * Math.PI) / 6;
        targetRotX = -(rootState.pointer.y * Math.PI) / 6;

        if (isSad) targetRotX -= 0.3; 
        if (isConfused) targetRotZ = -0.15; 
        if (isSpeaking) targetRotX += Math.sin(t * 8) * 0.03; 
        if (isExcited) targetRotY += Math.sin(t * 12) * 0.1; 

      } else {
        targetRotX = 0.2 + Math.sin(t) * 0.05; 
      }

      groupRef.current.rotation.y = THREE.MathUtils.lerp(groupRef.current.rotation.y, targetRotY, 0.1);
      groupRef.current.rotation.x = THREE.MathUtils.lerp(groupRef.current.rotation.x, targetRotX, 0.1);
      groupRef.current.rotation.z = THREE.MathUtils.lerp(groupRef.current.rotation.z, targetRotZ, 0.1);
    }

    if (leftArmRef.current && rightArmRef.current) {
      let armSwing = isSpeaking ? Math.sin(t * 8) * 0.2 : Math.sin(t * 2) * 0.05;
      if (isExcited) armSwing = Math.sin(t * 15) * 0.4;
      if (isSad || isSleepy) armSwing *= 0.2; 

      leftArmRef.current.rotation.x = THREE.MathUtils.lerp(leftArmRef.current.rotation.x, armSwing, 0.2);
      rightArmRef.current.rotation.x = THREE.MathUtils.lerp(rightArmRef.current.rotation.x, -armSwing, 0.2);
    }
  });

  const bodyMaterial = <meshPhysicalMaterial color="#e8e9ec" roughness={0.2} metalness={0.1} clearcoat={0.8} />;

  return (
    <group ref={groupRef} position={[0, 0, 0]}>
      <RoundedBox args={[2.2, 2.2, 2]} radius={0.4} smoothness={4} position={[0, 0, 0]}>{bodyMaterial}</RoundedBox>
      <mesh position={[-0.8, 1.2, 0]} rotation={[0, 0, 0.3]}><coneGeometry args={[0.3, 0.8, 16]} />{bodyMaterial}</mesh>
      <mesh position={[0.8, 1.2, 0]} rotation={[0, 0, -0.3]}><coneGeometry args={[0.3, 0.8, 16]} />{bodyMaterial}</mesh>
      
      <mesh ref={leftArmRef} position={[-1.3, -0.2, 0]}><capsuleGeometry args={[0.25, 0.8, 16, 16]} />{bodyMaterial}</mesh>
      <mesh ref={rightArmRef} position={[1.3, -0.2, 0]}><capsuleGeometry args={[0.25, 0.8, 16, 16]} />{bodyMaterial}</mesh>

      <RoundedBox args={[1.8, 1.5, 0.1]} radius={0.2} position={[0, 0, 1.01]}>
        <meshStandardMaterial color="#111" roughness={0.8} />
      </RoundedBox>

      <RoundedBox args={[1.6, 1.3, 0.05]} radius={0.15} position={[0, 0, 1.05]}>
        <meshPhysicalMaterial color="#000000" roughness={0.05} metalness={0.8} clearcoat={1} />
      </RoundedBox>

      <group position={[0, 0, 1.08]}>
        <Face state={state} emotion={emotion} colors={colors} />
      </group>

      <EmotionEffects state={state} emotion={emotion} colors={colors} />
      <SoundWaves isSpeaking={state === "speaking"} color={colors.glow} />
    </group>
  );
}

// ── صورت ──────────────────────────────────────────────
type FaceProps = {
  state: AIAvatarState;
  emotion: AIAvatarEmotion;
  colors: { glow: string; face: string; accent: string };
};
function Face({ state, emotion, colors }: FaceProps) {
  const isSpeaking = state === "speaking";
  const expressions = useMemo(() => {
    const map: Record<AIAvatarEmotion, { eye: string; mouth: string }> = {
      neutral: { eye: "square", mouth: "flat" },
      happy: { eye: "circle", mouth: "smile" },
      excited: { eye: "star", mouth: "bigsmile" },
      sad: { eye: "halfline", mouth: "frown" },
      confused: { eye: "circle", mouth: "wave" },
      surprised: { eye: "circle", mouth: "o" },
      love: { eye: "heart", mouth: "smile" },
      annoyed: { eye: "halfline", mouth: "flat" },
      angry: { eye: "x", mouth: "frown" },
      sleepy: { eye: "halfline", mouth: "flat" },
    };
    return map[emotion];
  }, [emotion]);

  return (
    <>
      <group position={[-0.35, 0.2, 0]}>
        <Eye type={expressions.eye} color={colors.face} isIdle={state === "idle"} />
      </group>
      <group position={[0.35, 0.2, 0]}>
        <Eye type={expressions.eye} color={colors.face} isIdle={state === "idle"} />
      </group>
      <group position={[0, -0.25, 0]}>
        <Mouth type={expressions.mouth} color={colors.face} isSpeaking={isSpeaking} isSurprised={emotion === 'surprised'} />
      </group>
    </>
  );
}

function Eye({ type, color, isIdle }: any) {
  const eyeRef = useRef<THREE.Group>(null);

  useFrame((state) => {
    if (!eyeRef.current) return;
    const t = state.clock.getElapsedTime();
    if (isIdle) {
      const blink = Math.sin(t * 3) > 0.95 ? 0.1 : 1;
      eyeRef.current.scale.y = THREE.MathUtils.lerp(eyeRef.current.scale.y, blink, 0.5);
    }
    if (type === "star") eyeRef.current.rotation.z -= 0.05;
    else eyeRef.current.rotation.z = 0;
  });

  const glowingMat = <meshBasicMaterial color={color} toneMapped={false} />;

  return (
    <group ref={eyeRef}>
      {type === "square" && <RoundedBox args={[0.25, 0.25, 0.02]} radius={0.05}>{glowingMat}</RoundedBox>}
      {type === "halfline" && <RoundedBox args={[0.25, 0.08, 0.02]} radius={0.02}>{glowingMat}</RoundedBox>}
      {type === "circle" && <Sphere args={[0.12, 16, 16]} scale={[1, 1, 0.2]}>{glowingMat}</Sphere>}
      {type === "heart" && <Text fontSize={0.35} color={color} anchorX="center" anchorY="middle">♥</Text>}
      {type === "x" && <Text fontSize={0.35} color={color} anchorX="center" anchorY="middle">X</Text>}
      {type === "star" && <Text fontSize={0.45} color={color} anchorX="center" anchorY="middle">★</Text>}
    </group>
  );
}

function Mouth({ type, color, isSpeaking, isSurprised }: any) {
  const mouthRef = useRef<THREE.Group>(null);

  useFrame((state) => {
    if (!mouthRef.current) return;
    const t = state.clock.getElapsedTime();
    
    if (isSpeaking) {
      const lipSync = 0.5 + Math.abs(Math.sin(t * 15) * 0.5 + Math.cos(t * 8) * 0.3);
      mouthRef.current.scale.y = THREE.MathUtils.lerp(mouthRef.current.scale.y, lipSync, 0.3);
    } else if (isSurprised) {
      mouthRef.current.scale.y = 1 + Math.abs(Math.sin(t * 4) * 0.4);
      mouthRef.current.scale.x = 1 + Math.abs(Math.sin(t * 4) * 0.4);
    } else {
      mouthRef.current.scale.y = THREE.MathUtils.lerp(mouthRef.current.scale.y, 1, 0.3);
      mouthRef.current.scale.x = THREE.MathUtils.lerp(mouthRef.current.scale.x, 1, 0.3);
    }
  });

  const glowingMat = <meshBasicMaterial color={color} toneMapped={false} />;

  return (
    <group ref={mouthRef}>
      {isSpeaking ? (
        <RoundedBox args={[0.35, 0.12, 0.02]} radius={0.05}>{glowingMat}</RoundedBox>
      ) : (
        <>
          {type === "flat" && <RoundedBox args={[0.35, 0.06, 0.02]} radius={0.02}>{glowingMat}</RoundedBox>}
          {type === "smile" && <Torus args={[0.15, 0.03, 16, 32, Math.PI]} rotation={[0, 0, Math.PI]}>{glowingMat}</Torus>}
          {type === "bigsmile" && <Torus args={[0.2, 0.04, 16, 32, Math.PI]} rotation={[0, 0, Math.PI]}>{glowingMat}</Torus>}
          {type === "frown" && <Torus args={[0.15, 0.03, 16, 32, Math.PI]} position={[0, -0.05, 0]}>{glowingMat}</Torus>}
          {type === "o" && <Torus args={[0.1, 0.04, 16, 32]}>{glowingMat}</Torus>}
          {type === "wave" && <Text fontSize={0.35} color={color} anchorX="center" anchorY="middle">~</Text>}
        </>
      )}
    </group>
  );
}

// ── افکت‌های هیجان‌انگیز محیطی و احساسات (با ارتفاع‌های بهینه‌سازی شده) ───
function EmotionEffects({ state, emotion, colors }: any) {
  return (
    <>
      {state === "thinking" && <SpinnerParticle color={colors.glow} />}

      {emotion === "love" && (
        <group position={[0, 1.2, 0]}>
          <FloatingParticle delay={0} speed={1.5} position={[-1.2, 0]} bobbing scaleBobbing>
            <Text fontSize={0.6} color={colors.accent}>♥</Text>
          </FloatingParticle>
          <FloatingParticle delay={1} speed={1} position={[1.2, -0.2]} bobbing scaleBobbing>
            <Text fontSize={0.4} color={colors.accent}>♥</Text>
          </FloatingParticle>
        </group>
      )}

      {emotion === "sleepy" && (
        <group position={[0.8, 1.1, 0]}>
          <FloatingParticle delay={0} speed={0.5} position={[0, 0]}>
            <Text fontSize={0.4} color={colors.accent}>Z</Text>
          </FloatingParticle>
          <FloatingParticle delay={1} speed={0.4} position={[0.5, 0.4]}>
            <Text fontSize={0.6} color={colors.accent}>Z</Text>
          </FloatingParticle>
        </group>
      )}

      {emotion === "surprised" && <ShockwaveParticle color={colors.glow} />}

      {emotion === "confused" && (
        <group position={[1.2, 1.3, 0]}>
           <FloatingParticle speed={1} bobbing spin>
             <Text fontSize={0.7} color={colors.glow}>?</Text>
           </FloatingParticle>
        </group>
      )}

      {emotion === "sad" && (
        <>
          <TearParticle x={-0.35} y={0.1} delay={0} />
          <TearParticle x={0.35} y={0.1} delay={1.5} />
        </>
      )}

      {/* ابر عصبانی که از حالت بُرش رهایی یافته است :) */}
      {emotion === "angry" && (
        <Sparkles count={40} scale={[2.5, 1.2, 1.5]} size={8} speed={3} opacity={0.7} position={[0, 1.25, -0.2]} color="#ef4444" noise={1} />
      )}

      {emotion === "excited" && (
        <Sparkles count={50} scale={4} size={6} speed={2} opacity={1} color={colors.glow} />
      )}
    </>
  );
}

// ── ابزارهای کمکی ───────────────────────────

function FloatingParticle({ children, delay = 0, speed = 1, position =[0, 0], bobbing=false, scaleBobbing=false, spin=false }: any) {
  const ref = useRef<THREE.Group>(null);
  useFrame((state) => {
    if (!ref.current) return;
    const t = state.clock.getElapsedTime() + delay;
    
    if (bobbing) {
       ref.current.position.y = position[1] + Math.sin(t * speed) * 0.2;
    } else {
       const y = (t * speed) % 2; 
       ref.current.position.y = y;
       ref.current.position.x = position[0] + Math.sin(t * 2) * 0.1;
       ref.current.traverse((child: any) => {
          if (child.material) {
            child.material.transparent = true;
            child.material.opacity = 1 - (y / 2);
          }
       });
    }

    if (scaleBobbing) ref.current.scale.setScalar(1 + Math.sin(t * speed * 2) * 0.2);
    if (spin) ref.current.rotation.y = t * 2;
  });

  return <group ref={ref} position={[position[0], position[1], 0]}>{children}</group>;
}

function TearParticle({ x, y, delay }: { x: number; y: number; delay: number }) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame((state) => {
    if (!ref.current) return;
    const t = (state.clock.getElapsedTime() + delay) * 0.8;
    const fallTime = t % 2;
    ref.current.position.y = y - (fallTime * 1.5);
    const material = ref.current.material as THREE.MeshBasicMaterial;
    material.opacity = fallTime < 1.8 ? 1 - (fallTime / 1.8) : 0;
  });
  return (
    <mesh ref={ref} position={[x, y, 1.1]}>
      <sphereGeometry args={[0.04, 8, 8]} />
      <meshBasicMaterial color="#93c5fd" transparent />
    </mesh>
  );
}

function SpinnerParticle({ color }: { color: string }) {
  const groupRef = useRef<THREE.Group>(null);
  useFrame((state) => {
    if (groupRef.current) groupRef.current.rotation.y -= 0.05;
  });
  return (
    <group ref={groupRef} position={[0, 1.6, 0]}>
      {[0, 1, 2].map((i) => (
        <mesh key={i} position={[Math.cos(i * (Math.PI*2/3)) * 0.35, 0, Math.sin(i * (Math.PI*2/3)) * 0.35]}>
          <sphereGeometry args={[0.06]} />
          <meshBasicMaterial color={color} />
        </mesh>
      ))}
    </group>
  );
}

function ShockwaveParticle({ color }: { color: string }) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame((state) => {
    if (!ref.current) return;
    const t = (state.clock.getElapsedTime() * 1.5) % 2;
    ref.current.scale.setScalar(t * 3 + 1);
    (ref.current.material as THREE.MeshBasicMaterial).opacity = 1 - (t / 2);
  });
  return (
    <mesh ref={ref} position={[0, 0, -1]}>
      <torusGeometry args={[1, 0.02, 16, 64]} />
      <meshBasicMaterial color={color} transparent depthWrite={false} />
    </mesh>
  );
}

function SoundWaves({ isSpeaking, color }: { isSpeaking: boolean; color: string }) {
  const leftRef = useRef<THREE.Group>(null);
  const rightRef = useRef<THREE.Group>(null);
  
  useFrame((state) => {
    const t = state.clock.getElapsedTime();
    if (!leftRef.current || !rightRef.current) return;

    leftRef.current.children.forEach((child, i) => {
      const scale = isSpeaking ? 1 + Math.abs(Math.sin(t * (10 + i * 5))) * 1.5 : 0;
      child.scale.y = THREE.MathUtils.lerp(child.scale.y, scale, 0.2);
    });
    
    rightRef.current.children.forEach((child, i) => {
      const scale = isSpeaking ? 1 + Math.abs(Math.cos(t * (12 + i * 4))) * 1.5 : 0;
      child.scale.y = THREE.MathUtils.lerp(child.scale.y, scale, 0.2);
    });
  });

  return (
    <group position={[0, -0.3, 0]}>
      <group ref={leftRef} position={[-1.4, 0, 0]}>
        {[0, 1, 2].map((i) => (
           <RoundedBox key={i} args={[0.08, 0.2, 0.08]} radius={0.03} position={[i * 0.15, 0, 0]}>
              <meshBasicMaterial color={color} toneMapped={false} />
           </RoundedBox>
        ))}
      </group>
      <group ref={rightRef} position={[1.1, 0, 0]}>
        {[0, 1, 2].map((i) => (
           <RoundedBox key={i} args={[0.08, 0.2, 0.08]} radius={0.03} position={[i * 0.15, 0, 0]}>
              <meshBasicMaterial color={color} toneMapped={false} />
           </RoundedBox>
        ))}
      </group>
    </group>
  );
}