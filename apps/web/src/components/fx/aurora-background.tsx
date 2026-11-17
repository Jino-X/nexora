/**
 * Full-screen animated backdrop: drifting aurora glows, a faded dot grid and film grain.
 * Pure CSS (transform-only animations), so it costs almost nothing and honours reduced motion.
 */
export function AuroraBackground({ intensity = "normal" }: { intensity?: "normal" | "soft" }) {
  const soft = intensity === "soft";
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div
        className="aurora-blob -top-[18vh] -left-[10vw] h-[62vh] w-[62vh]"
        style={{ background: "var(--aurora-1)", animation: "aurora-a 26s ease-in-out infinite" }}
      />
      <div
        className="aurora-blob top-[8vh] -right-[12vw] h-[58vh] w-[58vh]"
        style={{ background: "var(--aurora-2)", animation: "aurora-b 32s ease-in-out infinite" }}
      />
      <div
        className="aurora-blob -bottom-[22vh] left-[22vw] h-[56vh] w-[70vh]"
        style={{ background: "var(--aurora-3)", animation: "aurora-c 38s ease-in-out infinite" }}
      />
      {!soft && (
        <div
          className="aurora-blob right-[18vw] -bottom-[10vh] h-[40vh] w-[40vh]"
          style={{ background: "var(--aurora-4)", animation: "aurora-a 44s ease-in-out infinite reverse" }}
        />
      )}
      <div className="bg-dots absolute inset-0 [mask-image:radial-gradient(ellipse_80%_60%_at_50%_0%,black,transparent_75%)]" />
      <div className="bg-noise absolute inset-0 opacity-[0.035] mix-blend-overlay dark:opacity-[0.06]" />
    </div>
  );
}
