"use client";

import { useEffect, useRef } from "react";

export function CursorOrb() {
  const orbRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const orb = orbRef.current;
    const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (!orb || !finePointer.matches || reducedMotion.matches) return;

    let targetX = -20;
    let targetY = -20;
    let currentX = -20;
    let currentY = -20;
    let frame = 0;
    let releaseTimer = 0;

    const render = () => {
      currentX += (targetX - currentX) * 0.72;
      currentY += (targetY - currentY) * 0.72;
      orb.style.transform = "translate3d(" + (currentX - 7) + "px," + (currentY - 7) + "px,0)";
      frame = requestAnimationFrame(render);
    };
    const move = (event: PointerEvent) => {
      if (event.pointerType && event.pointerType !== "mouse") return;
      targetX = event.clientX;
      targetY = event.clientY;
      if (currentX < 0) { currentX = targetX; currentY = targetY; }
      orb.dataset.visible = "true";
    };
    const down = () => {
      window.clearTimeout(releaseTimer);
      orb.dataset.pressed = "true";
    };
    const up = () => {
      releaseTimer = window.setTimeout(() => { orb.dataset.pressed = "false"; }, 140);
    };
    const hide = () => { orb.dataset.visible = "false"; };

    window.addEventListener("pointermove", move, { passive: true });
    window.addEventListener("pointerdown", down, { passive: true });
    window.addEventListener("pointerup", up, { passive: true });
    document.documentElement.addEventListener("mouseleave", hide);
    frame = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(releaseTimer);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerdown", down);
      window.removeEventListener("pointerup", up);
      document.documentElement.removeEventListener("mouseleave", hide);
    };
  }, []);

  return <span ref={orbRef} className="cursor-orb" aria-hidden="true"><span className="cursor-orb-dot" /></span>;
}
