"use client";

import { useMemo } from "react";
import { motion } from "motion/react";

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

// Screen glow color per emotion
const emotionScreenColor: Record<AIAvatarEmotion, { glow: string; face: string; accent: string }> = {
  neutral:   { glow: "#ffffff", face: "#e8e8e8", accent: "#aaaaaa" },
  happy:     { glow: "#fcd34d", face: "#fef3c7", accent: "#f59e0b" },
  excited:   { glow: "#f9a8d4", face: "#fdf2f8", accent: "#ec4899" },
  sad:       { glow: "#93c5fd", face: "#dbeafe", accent: "#60a5fa" },
  confused:  { glow: "#c4b5fd", face: "#ede9fe", accent: "#a78bfa" },
  surprised: { glow: "#6ee7b7", face: "#d1fae5", accent: "#34d399" },
  love:      { glow: "#fda4af", face: "#ffe4e6", accent: "#f43f5e" },
  annoyed:   { glow: "#fdba74", face: "#ffedd5", accent: "#fb923c" },
  angry:     { glow: "#fca5a5", face: "#fee2e2", accent: "#ef4444" },
  sleepy:    { glow: "#a5b4fc", face: "#c7d2fe", accent: "#818cf8" },
};

export function AIAvatar({ state = "idle", emotion = "neutral", size = 200, className = "" }: Props) {
  const isThinking = state === "thinking";
  const isSpeaking = state === "speaking";
  const colors = emotionScreenColor[emotion];

  // Face expressions on the LED screen
  const faceExpression = useMemo(() => {
    const expressions: Record<AIAvatarEmotion, {
      leftEye: "square" | "halfline" | "circle" | "heart" | "x" | "star";
      rightEye: "square" | "halfline" | "circle" | "heart" | "x" | "star";
      mouth: "flat" | "smile" | "bigsmile" | "frown" | "o" | "wave" | "heart";
    }> = {
      neutral:   { leftEye: "square",   rightEye: "square",   mouth: "flat"      },
      happy:     { leftEye: "circle",   rightEye: "circle",   mouth: "smile"     },
      excited:   { leftEye: "star",     rightEye: "star",     mouth: "bigsmile"  },
      sad:       { leftEye: "halfline", rightEye: "halfline", mouth: "frown"     },
      confused:  { leftEye: "circle",   rightEye: "circle",   mouth: "wave"      },
      surprised: { leftEye: "circle",   rightEye: "circle",   mouth: "o"         },
      love:      { leftEye: "heart",    rightEye: "heart",    mouth: "smile"     },
      annoyed:   { leftEye: "halfline", rightEye: "halfline", mouth: "flat"      },
      angry:     { leftEye: "x",        rightEye: "x",        mouth: "frown"     },
      sleepy:    { leftEye: "halfline", rightEye: "halfline", mouth: "flat"      },
    };
    return expressions[emotion];
  }, [emotion]);

  const scale = size / 200;

  return (
    <motion.div
      className={`relative flex items-center justify-center select-none ${className}`}
      style={{ width: size, height: size * 1.1 }}
      animate={
        state === "idle"
          ? emotion === "sleepy"
            ? { y: [0, -2, 0] }
            : { y: [0, -4, 0] }
          : isSpeaking
          ? { y: [0, -2, 0] }
          : { y: 0 }
      }
      transition={{
        duration: isSpeaking ? 0.4 : emotion === "sleepy" ? 4 : 3.5,
        repeat: Infinity,
        ease: "easeInOut",
      }}
      aria-label={
        state === "thinking" ? "Assistant is thinking" :
        state === "speaking" ? "Assistant is speaking" :
        emotion !== "neutral" ? `AI feeling ${emotion}` : "AI Assistant"
      }
    >
      <svg
        width="100%"
        height="100%"
        viewBox="0 0 200 220"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        overflow="visible"
      >
        <defs>
          {/* Body gradient — soft white plastic (slightly darker) */}
          <radialGradient id="bodyGrad" cx="35%" cy="25%" r="70%">
            <stop offset="0%" stopColor="#e8e9ec" />
            <stop offset="60%" stopColor="#d0d2d6" />
            <stop offset="100%" stopColor="#a8abb2" />
          </radialGradient>

          {/* Screen gradient — deep black with inner glow */}
          <radialGradient id="screenGrad" cx="30%" cy="30%" r="65%">
            <stop offset="0%" stopColor="#1a1a1a" />
            <stop offset="100%" stopColor="#050505" />
          </radialGradient>

          {/* Screen edge bezel */}
          <radialGradient id="bezelGrad" cx="40%" cy="20%" r="65%">
            <stop offset="0%" stopColor="#555" />
            <stop offset="100%" stopColor="#111" />
          </radialGradient>

          {/* Arm gradient */}
          <radialGradient id="armGrad" cx="30%" cy="25%" r="70%">
            <stop offset="0%" stopColor="#e0e2e6" />
            <stop offset="100%" stopColor="#a0a4ac" />
          </radialGradient>

          {/* Ear gradient */}
          <radialGradient id="earGrad" cx="35%" cy="25%" r="70%">
            <stop offset="0%" stopColor="#e0e2e6" />
            <stop offset="100%" stopColor="#a0a4ac" />
          </radialGradient>

          {/* Shadow beneath robot */}
          <radialGradient id="shadowGrad" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#00000030" />
            <stop offset="100%" stopColor="#00000000" />
          </radialGradient>

          {/* Screen glow filter */}
          <filter id="screenGlow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* Soft body shadow */}
          <filter id="bodyShadow" x="-15%" y="-15%" width="130%" height="130%">
            <feDropShadow dx="0" dy="6" stdDeviation="10" floodColor="#00000025" />
          </filter>

          {/* LED scan-line pattern */}
          <pattern id="scanlines" x="0" y="0" width="60" height="4" patternUnits="userSpaceOnUse">
            <rect x="0" y="0" width="60" height="2" fill="white" opacity="0.04" />
          </pattern>
        </defs>

        {/* ── Ground shadow ── */}
        <ellipse cx="100" cy="210" rx="52" ry="10" fill="url(#shadowGrad)" />

        {/* ── Left arm ── */}
        <motion.g
          animate={
            isSpeaking
              ? { rotate: [-8, 8, -8] }
              : state === "idle"
              ? { rotate: [-3, 3, -3] }
              : { rotate: 0 }
          }
          transition={{
            duration: isSpeaking ? 0.4 : 3,
            repeat: Infinity,
            ease: "easeInOut",
          }}
          style={{ transformOrigin: "42px 120px" }}
        >
          <ellipse cx="30" cy="128" rx="14" ry="22" fill="url(#armGrad)" filter="url(#bodyShadow)" />
          {/* arm highlight */}
          <ellipse cx="25" cy="120" rx="5" ry="8" fill="white" opacity="0.4" />
        </motion.g>

        {/* ── Right arm ── */}
        <motion.g
          animate={
            isSpeaking
              ? { rotate: [8, -8, 8] }
              : state === "idle"
              ? { rotate: [3, -3, 3] }
              : { rotate: 0 }
          }
          transition={{
            duration: isSpeaking ? 0.4 : 3,
            repeat: Infinity,
            ease: "easeInOut",
            delay: 0.15,
          }}
          style={{ transformOrigin: "158px 120px" }}
        >
          <ellipse cx="170" cy="128" rx="14" ry="22" fill="url(#armGrad)" filter="url(#bodyShadow)" />
          {/* arm highlight */}
          <ellipse cx="165" cy="120" rx="5" ry="8" fill="white" opacity="0.4" />
        </motion.g>

        {/* ── Left cat ear (flat base attached to body) ── */}
        <path
          d="M 53 62 A 15 11 0 0 1 83 62 Z"
          fill="url(#earGrad)"
          transform="rotate(-15 68 52)"
          filter="url(#bodyShadow)"
        />
        <path
          d="M 60.5 57.5 A 7.5 5.5 0 0 1 75.5 57.5 Z"
          fill="white"
          opacity="0.5"
          transform="rotate(-15 68 52)"
        />

        {/* ── Right cat ear (flat base attached to body) ── */}
        <path
          d="M 117 62 A 15 11 0 0 1 147 62 Z"
          fill="url(#earGrad)"
          transform="rotate(15 132 52)"
          filter="url(#bodyShadow)"
        />
        <path
          d="M 124.5 57.5 A 7.5 5.5 0 0 1 139.5 57.5 Z"
          fill="white"
          opacity="0.5"
          transform="rotate(15 132 52)"
        />

        {/* ── Main body (rounded square head) ── */}
        <motion.rect
          x="42" y="62"
          width="116" height="118"
          rx="32"
          fill="url(#bodyGrad)"
          filter="url(#bodyShadow)"
          animate={
            isThinking
              ? { scale: [1, 1.02, 1] }
              : { scale: 1 }
          }
          transition={{ duration: 1.2, repeat: Infinity, ease: "easeInOut" }}
          style={{ transformOrigin: "100px 121px" }}
        />

        {/* Body top highlight */}
        <ellipse cx="82" cy="76" rx="28" ry="10" fill="white" opacity="0.35" style={{ filter: "blur(4px)" }} />

        {/* ── Screen bezel ── */}
        <rect x="55" y="78" width="90" height="82" rx="18" fill="url(#bezelGrad)" />

        {/* ── LED Screen ── */}
        <rect x="58" y="81" width="84" height="76" rx="16" fill="url(#screenGrad)" />

        {/* Scanline overlay */}
        <rect x="58" y="81" width="84" height="76" rx="16" fill="url(#scanlines)" />

        {/* Screen inner subtle glow from emotion */}
        <motion.rect
          x="58" y="81" width="84" height="76" rx="16"
          fill={colors.glow}
          opacity={0}
          animate={{ opacity: [0, 0.04, 0] }}
          transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
        />

        {/* ── FACE ELEMENTS on the screen (look around when idle) ── */}
        <motion.g
          filter="url(#screenGlow)"
          animate={
            state === "idle" && emotion !== "surprised" && emotion !== "angry" && emotion !== "sleepy"
              ? {
                  x: [0, -5, 0, 4, 0, 6, 0, -4, 0, 3, 0, -5, 0],
                  y: [0, 0, -2, -3, 0, 1, 0, 2, 0, -2, 0, 1, 0],
                }
              : { x: 0, y: 0 }
          }
          transition={{
            duration: 5,
            times: [0, 0.08, 0.15, 0.23, 0.31, 0.39, 0.46, 0.54, 0.62, 0.7, 0.77, 0.85, 1],
            repeat: state === "idle" && emotion !== "surprised" && emotion !== "angry" && emotion !== "sleepy" ? Infinity : 0,
            repeatType: "reverse",
            repeatDelay: 14,
            ease: "easeInOut",
          }}
        >
          {/* LEFT EYE */}
          <ScreenEye
            x={76} y={107}
            type={faceExpression.leftEye}
            color={colors.face}
            glow={colors.glow}
            accent={colors.accent}
            state={state}
            side="left"
            emotion={emotion}
          />

          {/* RIGHT EYE */}
          <ScreenEye
            x={114} y={107}
            type={faceExpression.rightEye}
            color={colors.face}
            glow={colors.glow}
            accent={colors.accent}
            state={state}
            side="right"
            emotion={emotion}
          />

          {/* MOUTH */}
          <ScreenMouth
            cx={100} cy={138}
            type={faceExpression.mouth}
            color={colors.face}
            glow={colors.glow}
            accent={colors.accent}
            isSpeaking={isSpeaking}
          />
        </motion.g>

        {/* Screen reflection shine */}
        <motion.rect
          x="62" y="84" width="38" height="20" rx="8"
          fill="white" opacity="0.06"
          animate={{ opacity: [0.05, 0.1, 0.05] }}
          transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
        />

        {/* ── THINKING: floating dots above head ── */}
        {isThinking && (
          <g>
            {[0, 1, 2].map((i) => (
              <motion.circle
                key={i}
                cx={86 + i * 14}
                cy={55}
                r={4}
                fill={colors.glow}
                opacity={0.9}
                animate={{
                  y: [0, -8, 0],
                  opacity: [0.4, 1, 0.4],
                }}
                transition={{
                  duration: 0.9,
                  repeat: Infinity,
                  delay: i * 0.22,
                  ease: "easeInOut",
                }}
              />
            ))}
          </g>
        )}

        {/* ── SPEAKING: soundwave outside body ── */}
        {isSpeaking && (
          <>
            {[0, 1, 2].map((i) => (
              <motion.rect
                key={i}
                x={153 + i * 7} y={110}
                width="3.5" height="12"
                rx="1.8"
                fill={colors.glow}
                animate={{ height: [12, 24, 12], y: [110, 104, 110], opacity: [0.5, 1, 0.5] }}
                transition={{ duration: 0.38, repeat: Infinity, delay: i * 0.1, ease: "easeInOut" }}
              />
            ))}
            {[0, 1, 2].map((i) => (
              <motion.rect
                key={`l${i}`}
                x={34 - i * 7} y={110}
                width="3.5" height="12"
                rx="1.8"
                fill={colors.glow}
                animate={{ height: [12, 24, 12], y: [110, 104, 110], opacity: [0.5, 1, 0.5] }}
                transition={{ duration: 0.38, repeat: Infinity, delay: i * 0.1, ease: "easeInOut" }}
              />
            ))}
          </>
        )}

        {/* ── EMOTION FX ── */}

        {/* LOVE: mini hearts floating up */}
        {emotion === "love" && [0, 1, 2].map((i) => (
          <motion.g key={i}
            animate={{ y: [0, -40], opacity: [0.9, 0] }}
            transition={{ duration: 1.8 + i * 0.3, repeat: Infinity, delay: i * 0.6, ease: "easeOut" }}
            style={{ transformOrigin: `${88 + i * 14}px 60px` }}
          >
            <text x={82 + i * 14} y={66} fontSize={10 + i * 2} fill={colors.accent} opacity={0.9}>♥</text>
          </motion.g>
        ))}

        {/* EXCITED: sparkles */}
        {emotion === "excited" && [0, 1, 2, 3].map((i) => {
          const angle = (i / 4) * Math.PI * 2;
          const bx = 100 + 62 * Math.cos(angle);
          const by = 121 + 62 * Math.sin(angle);
          return (
            <motion.g key={i}
              animate={{ scale: [0, 1.3, 0], opacity: [0, 1, 0] }}
              transition={{ duration: 0.85, repeat: Infinity, delay: i * 0.2, ease: "easeInOut" }}
              style={{ transformOrigin: `${bx}px ${by}px` }}
            >
              <line x1={bx - 5} y1={by} x2={bx + 5} y2={by} stroke={colors.glow} strokeWidth="2.5" strokeLinecap="round" />
              <line x1={bx} y1={by - 5} x2={bx} y2={by + 5} stroke={colors.glow} strokeWidth="2.5" strokeLinecap="round" />
            </motion.g>
          );
        })}

        {/* SAD: tear drop */}
        {emotion === "sad" && (
          <motion.ellipse cx="72" cy="114" rx="3" ry="5"
            fill={colors.glow} opacity={0.85}
            animate={{ cy: [114, 132], opacity: [0.85, 0], ry: [5, 4] }}
            transition={{ duration: 2.2, repeat: Infinity, ease: "easeIn" }}
          />
        )}

        {/* SURPRISED: ring burst */}
        {emotion === "surprised" && (
          <motion.circle cx="100" cy="119" r="55" fill="none"
            stroke={colors.glow} strokeWidth="2" opacity={0.3}
            animate={{ r: [50, 65], opacity: [0.4, 0] }}
            transition={{ duration: 0.8, repeat: Infinity, ease: "easeOut" }}
          />
        )}

        {/* ANGRY: steam puffs from ears */}
        {emotion === "angry" && [0, 1].map((i) => (
          <motion.ellipse key={i}
            cx={i === 0 ? 58 : 142} cy={54}
            rx={5} ry={4}
            fill={colors.accent} opacity={0.7}
            animate={{ cy: [54, 36], opacity: [0.7, 0], scale: [1, 1.6] }}
            transition={{ duration: 1, repeat: Infinity, delay: i * 0.3, ease: "easeOut" }}
          />
        ))}

        {/* SLEEPY: floating Z's */}
        {emotion === "sleepy" && [0, 1, 2].map((i) => (
          <motion.g key={i}
            animate={{ x: [0, 8], y: [-20, -50], opacity: [0.7, 0], rotate: [0, 10] }}
            transition={{ duration: 2.5 + i * 0.4, repeat: Infinity, delay: i * 0.8, ease: "easeOut" }}
            style={{ transformOrigin: `${95 + i * 8}px 55px` }}
          >
            <text x={90 + i * 10} y={58} fontSize={12 + i * 2} fill={colors.accent} opacity={0.8} fontWeight="bold">Z</text>
          </motion.g>
        ))}

      </svg>
    </motion.div>
  );
}

// ── Sub-component: Screen Eye ──────────────────────────────────────────────
function ScreenEye({
  x, y, type, color, glow, accent, state, side, emotion
}: {
  x: number; y: number;
  type: "square" | "halfline" | "circle" | "heart" | "x" | "star";
  color: string; glow: string; accent: string;
  state: AIAvatarState;
  side: "left" | "right";
  emotion?: AIAvatarEmotion;
}) {
  const isIdle = state === "idle";
  const isSleepy = emotion === "sleepy";

  if (type === "square") {
    return (
      <motion.g>
        {/* LED square eye — blink when idle */}
        <motion.rect
          x={x - 12} y={y - 12}
          width={24} height={24}
          rx={4}
          fill={glow}
          opacity={0.85}
          animate={isIdle ? { opacity: [0.7, 1, 0.7], scaleY: [1, 0.02, 1] } : { opacity: [0.8, 1, 0.8] }}
          transition={isIdle ? {
            opacity: { duration: 3.5, repeat: Infinity, ease: "easeInOut" },
            scaleY: { duration: 0.14, repeat: Infinity, repeatDelay: 3.5, ease: "easeInOut", delay: 0 }
          } : { duration: 1.5, repeat: Infinity }}
          style={{ transformOrigin: `${x}px ${y}px` }}
        />
        {/* horizontal scanlines inside */}
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <motion.rect
            key={i}
            x={x - 11} y={y - 11 + i * 4}
            width={22} height={1.5}
            fill="black" opacity={0.3}
          />
        ))}
      </motion.g>
    );
  }

  if (type === "halfline") {
    return (
      <motion.rect
        x={x - 12} y={y - 3}
        width={24} height={6}
        rx={3}
        fill={glow}
        opacity={0.85}
        animate={isSleepy ? { opacity: [0.6, 0.9, 0.6] } : isIdle ? { opacity: [0.7, 1, 0.7], scaleY: [1, 0.08, 1] } : { opacity: [0.7, 1, 0.7] }}
        transition={isSleepy ? { opacity: { duration: 2.5, repeat: Infinity, ease: "easeInOut" } } : isIdle ? {
          opacity: { duration: 1.5, repeat: Infinity, ease: "easeInOut" },
          scaleY: { duration: 0.14, repeat: Infinity, repeatDelay: 3.5, ease: "easeInOut", delay: 0 }
        } : { duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
        style={{ transformOrigin: `${x}px ${y}px` }}
      />
    );
  }

  if (type === "circle") {
    return (
      <motion.g>
        <motion.circle
          cx={x} cy={y} r={10}
          fill={glow}
          opacity={0.85}
          animate={isIdle ? { scaleY: [1, 0.02, 1], opacity: [0.8, 1, 0.8] } : { opacity: [0.8, 1, 0.8] }}
          transition={isIdle ? {
            scaleY: { duration: 0.14, repeat: Infinity, repeatDelay: 3.5, ease: "easeInOut", delay: 0 },
            opacity: { duration: 2, repeat: Infinity }
          } : { duration: 1.5, repeat: Infinity }}
          style={{ transformOrigin: `${x}px ${y}px` }}
        />
        <circle cx={x - 3} cy={y - 3} r={2.5} fill="black" opacity={0.3} />
      </motion.g>
    );
  }

  if (type === "heart") {
    return (
      <motion.g
        animate={{ scale: [1, 1.15, 1] }}
        transition={{ duration: 0.9, repeat: Infinity, ease: "easeInOut", delay: side === "right" ? 0.15 : 0 }}
        style={{ transformOrigin: `${x}px ${y}px` }}
      >
        <text x={x - 8} y={y + 7} fontSize={18} fill={accent} opacity={0.95}>♥</text>
      </motion.g>
    );
  }

  if (type === "x") {
    return (
      <motion.g
        animate={{ opacity: [0.8, 1, 0.8] }}
        transition={{ duration: 0.5, repeat: Infinity }}
      >
        <line x1={x - 9} y1={y - 9} x2={x + 9} y2={y + 9} stroke={accent} strokeWidth={4} strokeLinecap="round" />
        <line x1={x + 9} y1={y - 9} x2={x - 9} y2={y + 9} stroke={accent} strokeWidth={4} strokeLinecap="round" />
      </motion.g>
    );
  }

  if (type === "star") {
    const pts = Array.from({ length: 5 }).map((_, i) => {
      const ang = (i * 2 * Math.PI) / 5 - Math.PI / 2;
      const angIn = ang + Math.PI / 5;
      const or = 11;
      const ir = 5;
      return `${x + or * Math.cos(ang)},${y + or * Math.sin(ang)} ${x + ir * Math.cos(angIn)},${y + ir * Math.sin(angIn)}`;
    }).join(" ");
    return (
      <motion.polygon
        points={pts}
        fill={glow}
        opacity={0.9}
        animate={{ scale: [1, 1.12, 1], rotate: [0, 15, 0] }}
        transition={{ duration: 1, repeat: Infinity, ease: "easeInOut" }}
        style={{ transformOrigin: `${x}px ${y}px` }}
      />
    );
  }

  return null;
}

// ── Sub-component: Screen Mouth ───────────────────────────────────────────
function ScreenMouth({
  cx, cy, type, color, glow, accent, isSpeaking
}: {
  cx: number; cy: number;
  type: "flat" | "smile" | "bigsmile" | "frown" | "o" | "wave" | "heart";
  color: string; glow: string; accent: string;
  isSpeaking: boolean;
}) {
  if (isSpeaking) {
    return (
      <motion.rect
        x={cx - 14} y={cy - 8}
        width={28} height={16}
        rx={8}
        fill={glow}
        animate={{ height: [16, 26, 16], y: [cy - 8, cy - 13, cy - 8], width: [28, 32, 28], x: [cx - 14, cx - 16, cx - 14] }}
        transition={{ duration: 0.38, repeat: Infinity, ease: "easeInOut" }}
      />
    );
  }

  if (type === "flat") {
    return (
      <motion.rect
        x={cx - 16} y={cy - 3}
        width={32} height={6}
        rx={3}
        fill={glow} opacity={0.8}
        animate={{ opacity: [0.7, 1, 0.7] }}
        transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
      />
    );
  }

  if (type === "smile") {
    return (
      <motion.path
        d={`M ${cx - 16} ${cy - 2} Q ${cx} ${cy + 14} ${cx + 16} ${cy - 2}`}
        stroke={glow} strokeWidth={5} strokeLinecap="round" fill="none"
        animate={{ opacity: [0.8, 1, 0.8] }}
        transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
      />
    );
  }

  if (type === "bigsmile") {
    return (
      <motion.path
        d={`M ${cx - 18} ${cy - 4} Q ${cx} ${cy + 18} ${cx + 18} ${cy - 4}`}
        stroke={glow} strokeWidth={6} strokeLinecap="round" fill="none"
        animate={{ d: [`M ${cx - 18} ${cy - 4} Q ${cx} ${cy + 18} ${cx + 18} ${cy - 4}`, `M ${cx - 18} ${cy - 4} Q ${cx} ${cy + 22} ${cx + 18} ${cy - 4}`, `M ${cx - 18} ${cy - 4} Q ${cx} ${cy + 18} ${cx + 18} ${cy - 4}`] }}
        transition={{ duration: 0.6, repeat: Infinity, ease: "easeInOut" }}
      />
    );
  }

  if (type === "frown") {
    return (
      <motion.path
        d={`M ${cx - 14} ${cy + 6} Q ${cx} ${cy - 6} ${cx + 14} ${cy + 6}`}
        stroke={glow} strokeWidth={5} strokeLinecap="round" fill="none"
        animate={{ opacity: [0.7, 1, 0.7] }}
        transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
      />
    );
  }

  if (type === "o") {
    return (
      <motion.ellipse
        cx={cx} cy={cy}
        rx={10} ry={12}
        fill={glow} opacity={0.85}
        animate={{ ry: [12, 15, 12], rx: [10, 11, 10] }}
        transition={{ duration: 0.7, repeat: Infinity, ease: "easeInOut" }}
      />
    );
  }

  if (type === "wave") {
    return (
      <motion.path
        d={`M ${cx - 16} ${cy} Q ${cx - 8} ${cy - 8} ${cx} ${cy} Q ${cx + 8} ${cy + 8} ${cx + 16} ${cy}`}
        stroke={glow} strokeWidth={5} strokeLinecap="round" fill="none"
        animate={{ d: [`M ${cx - 16} ${cy} Q ${cx - 8} ${cy - 8} ${cx} ${cy} Q ${cx + 8} ${cy + 8} ${cx + 16} ${cy}`, `M ${cx - 16} ${cy} Q ${cx - 8} ${cy + 8} ${cx} ${cy} Q ${cx + 8} ${cy - 8} ${cx + 16} ${cy}`, `M ${cx - 16} ${cy} Q ${cx - 8} ${cy - 8} ${cx} ${cy} Q ${cx + 8} ${cy + 8} ${cx + 16} ${cy}`] }}
        transition={{ duration: 1.1, repeat: Infinity, ease: "easeInOut" }}
      />
    );
  }

  if (type === "heart") {
    return (
      <motion.text x={cx - 10} y={cy + 8} fontSize={20} fill={accent}
        animate={{ scale: [1, 1.12, 1] }}
        transition={{ duration: 1, repeat: Infinity, ease: "easeInOut" }}
        style={{ transformOrigin: `${cx}px ${cy}px` }}
      >♥</motion.text>
    );
  }

  return null;
}