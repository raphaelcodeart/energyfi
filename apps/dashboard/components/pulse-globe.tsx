"use client";

import { useEffect, useRef } from "react";

/*
 * PulseGlobe: a rotating 3D sphere of linked nodes drawn on a canvas, with
 * light pulses travelling along the links. It stands for the network and
 * leans toward the pointer.
 *
 * Plain canvas 2D with a hand-rolled perspective projection: no WebGL, no
 * dependencies. Drawing stops while the globe is off screen or the tab is
 * hidden, and reduced-motion users get a single still frame.
 */

type Vec = [number, number, number];

interface Pulse {
  link: number;
  t: number;
  speed: number;
}

/** Evenly spread points on a unit sphere (Fibonacci lattice). */
function fibonacciSphere(count: number): Vec[] {
  const points: Vec[] = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i++) {
    const y = 1 - (i / (count - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const theta = golden * i;
    points.push([Math.cos(theta) * r, y, Math.sin(theta) * r]);
  }
  return points;
}

/** Links each node to its nearest neighbours, without duplicates. */
function nearestLinks(points: Vec[], perNode: number): [number, number][] {
  const seen = new Set<string>();
  const links: [number, number][] = [];
  points.forEach((p, i) => {
    points
      .map((q, j) => ({ j, d: (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2 }))
      .filter(({ j }) => j !== i)
      .sort((a, b) => a.d - b.d)
      .slice(0, perNode)
      .forEach(({ j }) => {
        const key = i < j ? `${i}-${j}` : `${j}-${i}`;
        if (!seen.has(key)) {
          seen.add(key);
          links.push([Math.min(i, j), Math.max(i, j)]);
        }
      });
  });
  return links;
}

export function PulseGlobe({ size = 280, nodes = 90, className = "" }: { size?: number; nodes?: number; className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const points = fibonacciSphere(nodes);
    const links = nearestLinks(points, 3);
    const pulses: Pulse[] = Array.from({ length: 9 }, () => ({
      link: Math.floor(Math.random() * links.length),
      t: Math.random(),
      speed: 0.004 + Math.random() * 0.006,
    }));
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.scale(dpr, dpr);

    let angleY = 0.6;
    let tiltX = -0.35;
    let targetTiltX = -0.35;
    let lean = 0;
    let targetLean = 0;
    let visible = true;
    let frame = 0;

    const radius = size * 0.38;
    const center = size / 2;
    const focal = size * 1.6;

    function project(p: Vec): { x: number; y: number; z: number; scale: number } {
      const cosY = Math.cos(angleY + lean);
      const sinY = Math.sin(angleY + lean);
      const x1 = p[0] * cosY - p[2] * sinY;
      const z1 = p[0] * sinY + p[2] * cosY;
      const cosX = Math.cos(tiltX);
      const sinX = Math.sin(tiltX);
      const y2 = p[1] * cosX - z1 * sinX;
      const z2 = p[1] * sinX + z1 * cosX;
      const scale = focal / (focal + z2 * radius);
      return { x: center + x1 * radius * scale, y: center + y2 * radius * scale, z: z2, scale };
    }

    function draw() {
      ctx!.clearRect(0, 0, size, size);

      // Core glow behind the sphere.
      const glow = ctx!.createRadialGradient(center, center, radius * 0.1, center, center, radius * 1.35);
      glow.addColorStop(0, "rgba(90, 152, 255, 0.35)");
      glow.addColorStop(0.55, "rgba(40, 126, 255, 0.10)");
      glow.addColorStop(1, "rgba(40, 126, 255, 0)");
      ctx!.fillStyle = glow;
      ctx!.fillRect(0, 0, size, size);

      const projected = points.map(project);

      ctx!.lineWidth = 1;
      for (const [a, b] of links) {
        const pa = projected[a]!;
        const pb = projected[b]!;
        const depth = (2 - (pa.z + pb.z) / 2) / 3; // 0.33 at the back, 1 at the front
        ctx!.strokeStyle = `rgba(190, 217, 255, ${0.05 + depth * 0.32})`;
        ctx!.beginPath();
        ctx!.moveTo(pa.x, pa.y);
        ctx!.lineTo(pb.x, pb.y);
        ctx!.stroke();
      }

      for (const p of projected) {
        const depth = (1 - p.z) / 2;
        ctx!.fillStyle = `rgba(255, ${170 + depth * 70}, ${185 + depth * 60}, ${0.25 + depth * 0.75})`;
        ctx!.beginPath();
        ctx!.arc(p.x, p.y, 1.1 + depth * 2.2 * p.scale, 0, Math.PI * 2);
        ctx!.fill();
      }

      for (const pulse of pulses) {
        const [a, b] = links[pulse.link]!;
        const pa = projected[a]!;
        const pb = projected[b]!;
        const x = pa.x + (pb.x - pa.x) * pulse.t;
        const y = pa.y + (pb.y - pa.y) * pulse.t;
        const depth = (1 - (pa.z + (pb.z - pa.z) * pulse.t)) / 2;
        const g = ctx!.createRadialGradient(x, y, 0, x, y, 9);
        g.addColorStop(0, `rgba(255, 255, 255, ${0.5 + depth * 0.5})`);
        g.addColorStop(0.4, `rgba(71, 226, 255, ${0.25 + depth * 0.4})`);
        g.addColorStop(1, "rgba(71, 226, 255, 0)");
        ctx!.fillStyle = g;
        ctx!.beginPath();
        ctx!.arc(x, y, 9, 0, Math.PI * 2);
        ctx!.fill();
      }
    }

    function tick() {
      angleY += 0.0032;
      tiltX += (targetTiltX - tiltX) * 0.05;
      lean += (targetLean - lean) * 0.05;
      for (const pulse of pulses) {
        pulse.t += pulse.speed;
        if (pulse.t >= 1) {
          pulse.t = 0;
          pulse.link = Math.floor(Math.random() * links.length);
        }
      }
      draw();
      if (visible && !document.hidden) frame = requestAnimationFrame(tick);
    }

    function onPointer(event: PointerEvent) {
      const nx = event.clientX / window.innerWidth - 0.5;
      const ny = event.clientY / window.innerHeight - 0.5;
      targetLean = nx * 0.9;
      targetTiltX = -0.35 + ny * 0.6;
    }

    function restart() {
      cancelAnimationFrame(frame);
      if (visible && !document.hidden) frame = requestAnimationFrame(tick);
    }

    if (reduceMotion) {
      draw();
      return;
    }

    const observer = new IntersectionObserver(([entry]) => {
      visible = entry?.isIntersecting ?? true;
      restart();
    });
    observer.observe(canvas);
    window.addEventListener("pointermove", onPointer, { passive: true });
    document.addEventListener("visibilitychange", restart);
    restart();

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("pointermove", onPointer);
      document.removeEventListener("visibilitychange", restart);
    };
  }, [size, nodes]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className={className}
      style={{ width: size, height: size }}
    />
  );
}
