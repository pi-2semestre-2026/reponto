export function burstConfetti() {
  if (typeof window === "undefined") return;
  import("canvas-confetti").then((confetti) => {
    const fire = (ratio: number, opts: Record<string, unknown>) =>
      confetti.default({
        origin: { y: 0.6 },
        colors: ["#1D5C3F", "#2E8B5F", "#FF6320", "#F2B824", "#F3EDDE"],
        disableForReducedMotion: true,
        ...opts,
        particleCount: Math.floor(220 * ratio),
      });
    fire(0.25, { spread: 26, startVelocity: 55 });
    fire(0.2, { spread: 60 });
    fire(0.35, { spread: 100, decay: 0.91, scalar: 0.9 });
    fire(0.1, { spread: 120, startVelocity: 25, decay: 0.92, scalar: 1.2 });
    fire(0.1, { spread: 120, startVelocity: 45 });
  });
}