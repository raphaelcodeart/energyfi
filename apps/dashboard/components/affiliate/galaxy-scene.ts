/*
 * The 3D scene of the virtual tour, plain three.js (no React inside): one
 * instanced mesh for every person, one line set for every sponsor link, a
 * glow for who has points this month, and "energy" travelling from each
 * buyer up to the viewer along the real sponsor chain (BCT climbs the tree).
 * The React layer (network-galaxy.tsx) drives it through a few methods and
 * listens to picks; names float as DOM labels placed here every frame.
 */

import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import { at, bounds, branchOf, levelColor, pathTo, type Star } from "@/lib/galaxy";

export type SceneOptions = {
  reducedMotion: boolean;
  lowPower: boolean;
  onPick: (index: number | null) => void;
  onHover: (index: number | null) => void;
  /** The person moved the camera themselves (stops the tour). */
  onUserMove: () => void;
};

export type LabelSpec = { index: number; kind: "focus" | "child" | "selected" | "hover" };

const BG = 0x000106;
const MAX_PARTICLES = 420;
/** The path from the viewer to the branch in view: gold. */
const PATH_RGB = [1.6, 1.25, 0.45];

const num0 = (a: ArrayLike<number>, i: number): number => a[i] ?? 0;

function glowTexture(): THREE.Texture {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, "rgba(255,255,255,1)");
  grad.addColorStop(0.25, "rgba(255,255,255,0.55)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 64, 64);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

type Flight = {
  from: THREE.Vector3; to: THREE.Vector3; fromTarget: THREE.Vector3; toTarget: THREE.Vector3;
  start: number; duration: number; arc: number;
};

type Particle = { path: number[]; seg: number; t: number; speed: number };

export class GalaxyScene {
  private renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera: THREE.PerspectiveCamera;
  private controls: OrbitControls;
  private composer: EffectComposer | null = null;
  private mesh: THREE.InstancedMesh;
  private links: THREE.LineSegments;
  private glow: THREE.Points;
  private flow: THREE.Points | null = null;
  private particles: Particle[] = [];
  private base: Float32Array;
  private linkBase: Float32Array;
  private linkOf: number[] = [];
  private flight: Flight | null = null;
  private raycaster = new THREE.Raycaster();
  private pointer = new THREE.Vector2();
  private pointerMoved = false;
  private down: { x: number; y: number } | null = null;
  private hovered: number | null = null;
  private selected: number | null = null;
  private labels = new Map<number, HTMLDivElement>();
  private resize: ResizeObserver;
  private clock = new THREE.Clock();
  private extent: number;
  private idleUntil = 0;
  private tmpM = new THREE.Matrix4();
  private tmpV = new THREE.Vector3();
  private tmpQ = new THREE.Quaternion();
  private tmpS = new THREE.Vector3();
  private disposed = false;

  constructor(private host: HTMLElement, private labelLayer: HTMLElement, private stars: Star[], private opts: SceneOptions) {
    const { lowPower } = opts;
    this.renderer = new THREE.WebGLRenderer({ antialias: !lowPower, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, lowPower ? 1.25 : 1.75));
    this.renderer.setClearColor(BG, 1);
    this.renderer.domElement.style.display = "block";
    this.renderer.domElement.style.touchAction = "none";
    host.appendChild(this.renderer.domElement);

    const all = stars.map((s) => s.index);
    const b = bounds(stars, all);
    this.extent = b.radius;
    this.scene.fog = new THREE.FogExp2(BG, 0.55 / Math.max(this.extent, 20));

    this.camera = new THREE.PerspectiveCamera(45, 1, 0.1, this.extent * 30 + 500);
    this.camera.position.set(0, this.extent * 1.2, this.extent * 4.2);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.minDistance = 1.5;
    this.controls.maxDistance = this.extent * 6 + 60;
    this.controls.autoRotate = !opts.reducedMotion;
    this.controls.autoRotateSpeed = 0.35;
    this.controls.addEventListener("start", this.onControlStart);

    // People.
    const geo = new THREE.IcosahedronGeometry(1, lowPower ? 1 : 2);
    // Lit spheres (they read as planets, not discs); the light rides with
    // the camera so the side in view is always lit.
    const mat = new THREE.MeshLambertMaterial({ toneMapped: false });
    this.scene.add(new THREE.HemisphereLight(0xbfd4ff, 0x0a1030, 1.1));
    const key = new THREE.DirectionalLight(0xffffff, 1.6);
    key.position.set(0.4, 0.6, 0);
    key.target.position.set(0, 0, -1);
    this.camera.add(key, key.target);
    this.scene.add(this.camera);
    this.mesh = new THREE.InstancedMesh(geo, mat, Math.max(1, stars.length));
    this.base = new Float32Array(stars.length * 3);
    const col = new THREE.Color();
    stars.forEach((s, i) => {
      this.tmpM.compose(this.tmpV.set(s.x, s.y, s.z), this.tmpQ.identity(), this.tmpS.setScalar(s.r));
      this.mesh.setMatrixAt(i, this.tmpM);
      col.set(s.parent < 0 ? "#ffe9a8" : levelColor(s.level));
      const active = s.bct > 0 || s.bcp > 0;
      const k = s.parent < 0 ? 2.4 : s.gone ? 0.22 : active ? 1.7 : 0.6;
      if (s.gone) col.lerp(new THREE.Color("#ff4d6d"), 0.5);
      col.multiplyScalar(k);
      this.base.set([col.r, col.g, col.b], i * 3);
      this.mesh.setColorAt(i, col);
    });
    this.mesh.instanceMatrix.needsUpdate = true;
    if (this.mesh.instanceColor) this.mesh.instanceColor.needsUpdate = true;
    this.mesh.computeBoundingSphere();
    this.scene.add(this.mesh);

    // Sponsor links.
    const linkPos: number[] = [];
    const linkCol: number[] = [];
    stars.forEach((s) => {
      if (s.parent < 0) return;
      const p = at(stars, s.parent);
      this.linkOf[s.index] = linkPos.length / 6;
      linkPos.push(p.x, p.y, p.z, s.x, s.y, s.z);
      const b0 = this.base;
      const pi = p.index * 3, si = s.index * 3;
      linkCol.push(num0(b0, pi) * 0.25, num0(b0, pi + 1) * 0.25, num0(b0, pi + 2) * 0.3,
        num0(b0, si) * 0.35, num0(b0, si + 1) * 0.35, num0(b0, si + 2) * 0.4);
    });
    this.linkBase = new Float32Array(linkCol);
    const lg = new THREE.BufferGeometry();
    lg.setAttribute("position", new THREE.Float32BufferAttribute(linkPos, 3));
    lg.setAttribute("color", new THREE.Float32BufferAttribute(linkCol, 3));
    this.links = new THREE.LineSegments(lg, new THREE.LineBasicMaterial({
      vertexColors: true, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false,
    }));
    this.scene.add(this.links);

    // Glow around who has points this month (and the viewer).
    const tex = glowTexture();
    const gp: number[] = [];
    const gc: number[] = [];
    stars.forEach((s) => {
      if (!(s.parent < 0 || s.bct > 0 || s.bcp > 0) || s.gone) return;
      gp.push(s.x, s.y, s.z);
      col.set(s.parent < 0 ? "#ffd36b" : levelColor(s.level));
      gc.push(col.r, col.g, col.b);
    });
    const gg = new THREE.BufferGeometry();
    gg.setAttribute("position", new THREE.Float32BufferAttribute(gp, 3));
    gg.setAttribute("color", new THREE.Float32BufferAttribute(gc, 3));
    this.glow = new THREE.Points(gg, new THREE.PointsMaterial({
      size: 3.2, map: tex, vertexColors: true, transparent: true, opacity: 0.75, depthWrite: false,
      blending: THREE.AdditiveBlending, sizeAttenuation: true, toneMapped: false,
    }));
    this.scene.add(this.glow);

    this.buildFlow(tex);
    this.buildSky();

    if (!lowPower) {
      this.composer = new EffectComposer(this.renderer);
      this.composer.addPass(new RenderPass(this.scene, this.camera));
      this.composer.addPass(new UnrealBloomPass(new THREE.Vector2(256, 256), 0.85, 0.55, 0.78));
      this.composer.addPass(new OutputPass());
    }

    this.resize = new ResizeObserver(() => this.fit());
    this.resize.observe(host);
    this.fit();

    const el = this.renderer.domElement;
    el.addEventListener("pointermove", this.onPointerMove);
    el.addEventListener("pointerdown", this.onPointerDown);
    el.addEventListener("pointerup", this.onPointerUp);
    el.addEventListener("pointerleave", this.onPointerLeave);

    this.renderer.setAnimationLoop(this.tick);
  }

  /** Points flowing from every buyer up to the viewer, along the real chain. */
  private buildFlow(tex: THREE.Texture) {
    const buyers = this.stars.filter((s) => s.parent >= 0 && s.bcp > 0 && !s.gone);
    if (!buyers.length) return;
    const weight = buyers.reduce((a, s) => a + Math.sqrt(s.bcp), 0);
    for (const s of buyers) {
      const n = Math.max(1, Math.round((Math.sqrt(s.bcp) / weight) * MAX_PARTICLES));
      const path = pathTo(this.stars, s.index).reverse(); // buyer → viewer
      for (let k = 0; k < n && this.particles.length < MAX_PARTICLES; k++) {
        this.particles.push({ path, seg: 0, t: Math.random(), speed: 0.35 + Math.random() * 0.35 });
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(new Float32Array(this.particles.length * 3), 3));
    this.flow = new THREE.Points(g, new THREE.PointsMaterial({
      size: 0.9, map: tex, color: new THREE.Color("#ffe08a").multiplyScalar(1.6), transparent: true, opacity: 0.95,
      depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false,
    }));
    this.scene.add(this.flow);
  }

  private buildSky() {
    const n = this.opts.lowPower ? 900 : 2200;
    const pos = new Float32Array(n * 3);
    const R = this.extent * 4 + 120;
    for (let i = 0; i < n; i++) {
      const u = Math.random() * 2 - 1;
      const phi = Math.random() * Math.PI * 2;
      const r = R * (1 + Math.random() * 1.5);
      const s = Math.sqrt(1 - u * u);
      pos.set([r * s * Math.cos(phi), r * u, r * s * Math.sin(phi)], i * 3);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    const sky = new THREE.Points(g, new THREE.PointsMaterial({ size: 1.4, sizeAttenuation: false, color: 0x8fa6d6, transparent: true, opacity: 0.7, fog: false }));
    this.scene.add(sky);
  }

  private fit() {
    const w = Math.max(1, this.host.clientWidth);
    const h = Math.max(1, this.host.clientHeight);
    this.renderer.setSize(w, h, false);
    this.renderer.domElement.style.width = `${w}px`;
    this.renderer.domElement.style.height = `${h}px`;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.composer?.setSize(w, h);
  }

  // --- Camera -----------------------------------------------------------------

  /** Flies to a person, framing them and their directs. */
  flyTo(index: number, { duration = 1.6, intro = false }: { duration?: number; intro?: boolean } = {}) {
    const s = at(this.stars, index);
    if (!s) return;
    const frame = [index, ...s.children.slice(0, 200)];
    const b = bounds(this.stars, frame);
    const toTarget = new THREE.Vector3(b.cx, b.cy, b.cz);
    const fov = (this.camera.fov * Math.PI) / 180;
    const dist = Math.max(6, (b.radius / Math.sin(fov / 2)) * 0.95);
    // Look at the branch from the side (and a little from above), so the
    // person and their directs open across the screen instead of the
    // person filling it from up close.
    let dir: THREE.Vector3;
    if (s.parent >= 0) {
      const p = at(this.stars, s.parent);
      const out = new THREE.Vector3(s.x - p.x, s.y - p.y, s.z - p.z).normalize();
      const side = new THREE.Vector3().crossVectors(out, new THREE.Vector3(0, 1, 0));
      if (side.lengthSq() < 0.01) side.set(1, 0, 0);
      side.normalize();
      // Keep the side the camera is already on: no needless half-turns.
      if (side.dot(this.camera.position.clone().sub(toTarget)) < 0) side.negate();
      dir = side.multiplyScalar(0.9).add(out.multiplyScalar(-0.3));
    } else {
      dir = this.camera.position.clone().sub(this.controls.target).normalize();
      if (!isFinite(dir.x) || dir.lengthSq() < 0.5) dir = new THREE.Vector3(0, 0.3, 1).normalize();
    }
    dir.y += 0.4;
    dir.normalize();
    const to = toTarget.clone().add(dir.multiplyScalar(dist));
    const reduced = this.opts.reducedMotion;
    this.flight = {
      from: this.camera.position.clone(), to,
      fromTarget: this.controls.target.clone(), toTarget,
      start: this.clock.getElapsedTime(), duration: reduced ? 0.001 : intro ? 3.2 : duration,
      arc: reduced ? 0 : Math.min(40, this.camera.position.distanceTo(to) * 0.25),
    };
    this.controls.enabled = false;
    this.controls.autoRotate = false;
    this.idleUntil = this.clock.getElapsedTime() + 9;
  }

  // --- Highlight ----------------------------------------------------------------

  /** Lights up a branch (and the path to it); everyone else fades. */
  setFocus(index: number) {
    const inside = new Uint8Array(this.stars.length);
    for (const i of branchOf(this.stars, index)) inside[i] = 1;
    const onPath = new Uint8Array(this.stars.length);
    for (const i of pathTo(this.stars, index)) onPath[i] = 1;
    const col = new THREE.Color();
    for (let i = 0; i < this.stars.length; i++) {
      const k = inside[i] ? 1 : onPath[i] ? 0.9 : 0.12;
      col.setRGB(num0(this.base, i * 3) * k, num0(this.base, i * 3 + 1) * k, num0(this.base, i * 3 + 2) * k);
      this.mesh.setColorAt(i, col);
    }
    if (this.mesh.instanceColor) this.mesh.instanceColor.needsUpdate = true;
    const attr = this.links.geometry.getAttribute("color") as THREE.BufferAttribute;
    const arr = attr.array as Float32Array;
    for (const s of this.stars) {
      if (s.parent < 0) continue;
      const li = this.linkOf[s.index] ?? 0;
      const path = onPath[s.index] && onPath[s.parent];
      const k = path ? 0 : inside[s.index] ? 1.25 : 0.12;
      for (let j = 0; j < 6; j++) arr[li * 6 + j] = path ? (PATH_RGB[j % 3] ?? 1) : num0(this.linkBase, li * 6 + j) * k;
    }
    attr.needsUpdate = true;
  }

  setSelected(index: number | null) {
    if (this.selected !== null) this.scaleStar(this.selected, 1);
    this.selected = index;
  }

  private scaleStar(i: number, k: number) {
    const s = at(this.stars, i);
    this.tmpM.compose(this.tmpV.set(s.x, s.y, s.z), this.tmpQ.identity(), this.tmpS.setScalar(s.r * k));
    this.mesh.setMatrixAt(i, this.tmpM);
    this.mesh.instanceMatrix.needsUpdate = true;
  }

  // --- Labels -------------------------------------------------------------------

  setLabels(specs: LabelSpec[]) {
    const keep = new Set(specs.map((s) => s.index));
    for (const [i, el] of this.labels) {
      if (!keep.has(i)) { el.remove(); this.labels.delete(i); }
    }
    for (const spec of specs) {
      const s = at(this.stars, spec.index);
      let el = this.labels.get(spec.index);
      if (!el) {
        el = document.createElement("div");
        el.className = "galaxy-label";
        const name = document.createElement("b");
        name.textContent = s.name;
        const sub = document.createElement("span");
        sub.textContent = s.children.length ? `${s.size + 1} persone` : s.code;
        el.append(name, sub);
        this.labelLayer.appendChild(el);
        this.labels.set(spec.index, el);
      }
      el.dataset.kind = spec.kind;
    }
  }

  private placeLabels() {
    const w = this.host.clientWidth;
    const h = this.host.clientHeight;
    for (const [i, el] of this.labels) {
      const s = at(this.stars, i);
      this.tmpV.set(s.x, s.y + s.r * 1.25, s.z).project(this.camera);
      if (this.tmpV.z > 1 || this.tmpV.z < -1) { el.style.opacity = "0"; continue; }
      const x = (this.tmpV.x * 0.5 + 0.5) * w;
      const y = (-this.tmpV.y * 0.5 + 0.5) * h;
      const d = this.camera.position.distanceTo(this.tmpS.set(s.x, s.y, s.z));
      const fade = el.dataset.kind === "child" ? Math.max(0, Math.min(1, 1.6 - d / (this.extent * 0.9 + 25))) : 1;
      el.style.opacity = String(fade);
      el.style.transform = `translate(-50%, -100%) translate(${x.toFixed(1)}px, ${y.toFixed(1)}px)`;
    }
  }

  // --- Input ----------------------------------------------------------------------

  private onControlStart = () => {
    if (this.flight) return;
    this.controls.autoRotate = false;
    this.idleUntil = this.clock.getElapsedTime() + 12;
    this.opts.onUserMove();
  };

  private setPointer(e: PointerEvent) {
    const r = this.renderer.domElement.getBoundingClientRect();
    this.pointer.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  }

  private onPointerMove = (e: PointerEvent) => {
    if (e.pointerType === "touch") return;
    this.setPointer(e);
    this.pointerMoved = true;
  };

  private onPointerDown = (e: PointerEvent) => {
    this.down = { x: e.clientX, y: e.clientY };
  };

  private onPointerUp = (e: PointerEvent) => {
    if (!this.down || Math.hypot(e.clientX - this.down.x, e.clientY - this.down.y) > 6) { this.down = null; return; }
    this.down = null;
    this.setPointer(e);
    this.opts.onPick(this.pick());
  };

  private onPointerLeave = () => {
    if (this.hovered !== null) { this.hovered = null; this.opts.onHover(null); }
    this.renderer.domElement.style.cursor = "";
  };

  private pick(): number | null {
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const hit = this.raycaster.intersectObject(this.mesh, false)[0];
    return hit?.instanceId ?? null;
  }

  // --- Frame ------------------------------------------------------------------------

  private tick = () => {
    if (this.disposed) return;
    const dt = Math.min(this.clock.getDelta(), 0.05);
    const now = this.clock.getElapsedTime();

    if (this.flight) {
      const f = this.flight;
      const t = Math.min(1, (now - f.start) / f.duration);
      const e = ease(t);
      this.camera.position.lerpVectors(f.from, f.to, e);
      this.camera.position.y += Math.sin(Math.PI * e) * f.arc;
      this.controls.target.lerpVectors(f.fromTarget, f.toTarget, e);
      if (t >= 1) {
        this.flight = null;
        this.controls.enabled = true;
      }
    } else if (!this.opts.reducedMotion && !this.controls.autoRotate && now > this.idleUntil) {
      this.controls.autoRotate = true;
    }
    this.controls.update();

    if (this.pointerMoved && !this.flight) {
      this.pointerMoved = false;
      const i = this.pick();
      if (i !== this.hovered) {
        this.hovered = i;
        this.renderer.domElement.style.cursor = i === null ? "" : "pointer";
        this.opts.onHover(i);
      }
    }

    if (this.selected !== null && !this.opts.reducedMotion) this.scaleStar(this.selected, 1.18 + Math.sin(now * 3.2) * 0.1);
    if (this.flow && !this.opts.reducedMotion) this.moveParticles(dt);

    this.placeLabels();
    if (this.composer) this.composer.render(dt);
    else this.renderer.render(this.scene, this.camera);
  };

  private moveParticles(dt: number) {
    const attr = this.flow!.geometry.getAttribute("position") as THREE.BufferAttribute;
    const arr = attr.array as Float32Array;
    this.particles.forEach((p, k) => {
      p.t += dt * p.speed * 1.4;
      while (p.t >= 1) {
        p.t -= 1;
        p.seg += 1;
        if (p.seg >= p.path.length - 1) { p.seg = 0; p.t = Math.random() * 0.2; }
      }
      const a = at(this.stars, at(p.path, p.seg));
      const b = at(this.stars, at(p.path, Math.min(p.seg + 1, p.path.length - 1)));
      arr[k * 3] = a.x + (b.x - a.x) * p.t;
      arr[k * 3 + 1] = a.y + (b.y - a.y) * p.t;
      arr[k * 3 + 2] = a.z + (b.z - a.z) * p.t;
    });
    attr.needsUpdate = true;
  }

  dispose() {
    this.disposed = true;
    this.renderer.setAnimationLoop(null);
    this.resize.disconnect();
    const el = this.renderer.domElement;
    el.removeEventListener("pointermove", this.onPointerMove);
    el.removeEventListener("pointerdown", this.onPointerDown);
    el.removeEventListener("pointerup", this.onPointerUp);
    el.removeEventListener("pointerleave", this.onPointerLeave);
    this.controls.removeEventListener("start", this.onControlStart);
    this.controls.dispose();
    for (const el2 of this.labels.values()) el2.remove();
    this.labels.clear();
    this.scene.traverse((o) => {
      const m = o as THREE.Mesh;
      m.geometry?.dispose();
      const mats = Array.isArray(m.material) ? m.material : m.material ? [m.material] : [];
      for (const mt of mats) {
        (mt as THREE.PointsMaterial).map?.dispose();
        mt.dispose();
      }
    });
    this.composer?.dispose();
    this.renderer.dispose();
    el.remove();
  }
}

export function webglAvailable(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}
