/*
 * The virtual tour of a Digital Ambassador's own network: the data the server
 * sends in one answer (GET /affiliate/me/network/galaxy) and where each
 * person sits in space. Pure functions, no three.js: the scene only draws.
 *
 * Layout ("cone tree" in 3D): the viewer is at the centre and their directs
 * sit on a sphere around them; every other person's directs open on a cap
 * pointing away from their sponsor, the biggest branch straight ahead. Caps
 * and distances grow with the number of directs, so a big leg looks big and
 * the same network always lands in the same place.
 */

export type GalaxyAnswer = {
  scope: string;
  period: string;
  people: number;
  shown: number;
  truncated: boolean;
  fields: string[];
  nodes: unknown[][];
};

export type Star = {
  index: number;
  id: string;
  parent: number;
  name: string;
  code: string;
  level: number | null;
  nextLevel: number | null;
  bcp: number;
  bct: number;
  size: number;
  directs: number;
  depth: number;
  paid: boolean;
  gone: boolean;
  qualifyingLegs: number;
  activeLegs: number;
  children: number[];
  /** Position in space. */
  x: number;
  y: number;
  z: number;
  /** Radius of the sphere drawn. */
  r: number;
};

/** A row that must exist (indexes come from the same answer). */
export function at<T>(list: readonly T[], i: number): T {
  const v = list[i];
  if (v === undefined) throw new Error(`galaxy: missing row ${i}`);
  return v;
}

export function decodeGalaxy(answer: GalaxyAnswer): Star[] {
  const f = new Map(answer.fields.map((k, i) => [k, i]));
  const get = (row: unknown[], k: string) => row[f.get(k) ?? -1];
  const stars: Star[] = answer.nodes.map((row, index) => ({
    index,
    id: String(get(row, "id")),
    parent: Number(get(row, "parent") ?? -1),
    name: String(get(row, "name") ?? ""),
    code: String(get(row, "code") ?? ""),
    level: (get(row, "level") as number | null) ?? null,
    nextLevel: (get(row, "next_level") as number | null) ?? null,
    bcp: Number(get(row, "bcp") ?? 0),
    bct: Number(get(row, "bct") ?? 0),
    size: Number(get(row, "size") ?? 0),
    directs: Number(get(row, "directs") ?? 0),
    depth: Number(get(row, "depth") ?? 0),
    paid: Boolean(get(row, "paid")),
    gone: Boolean(get(row, "gone")),
    qualifyingLegs: Number(get(row, "qualifying_legs") ?? 0),
    activeLegs: Number(get(row, "active_legs") ?? 0),
    children: [],
    x: 0, y: 0, z: 0, r: 0,
  }));
  for (const s of stars) if (s.parent >= 0 && s.parent < stars.length) at(stars, s.parent).children.push(s.index);
  layout(stars);
  return stars;
}

const GOLDEN = Math.PI * (3 - Math.sqrt(5));

type V = [number, number, number];

function norm(v: V): V {
  const l = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / l, v[1] / l, v[2] / l];
}

function cross(a: V, b: V): V {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}

/** Two unit vectors perpendicular to `d` (and to each other). */
function basis(d: V): [V, V] {
  const helper: V = Math.abs(d[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0];
  const u = norm(cross(d, helper));
  return [u, cross(d, u)];
}

export function starRadius(s: Star): number {
  return s.parent < 0 ? 1.5 : 0.24 + 0.1 * Math.log2(s.size + 2);
}

function layout(stars: Star[]): void {
  if (!stars.length) return;
  const dir: V[] = stars.map((): V => [0, 0, 1]);
  const root = at(stars, 0);
  root.r = starRadius(root);
  // Breadth order: parents are placed before their directs.
  for (const s of stars) {
    const k = s.children.length;
    if (!k) continue;
    const isRoot = s.parent < 0;
    const d = at(dir, s.index);
    const [u, w] = basis(d);
    // Full sphere around the viewer; a cap pointing outwards below.
    const cap = isRoot ? Math.PI : Math.min(Math.PI / 2.1, 0.32 + 0.11 * Math.sqrt(k));
    const minCos = Math.cos(cap);
    const reach = (isRoot ? 9 : 3.2) + (isRoot ? 2.6 : 1.25) * Math.sqrt(k);
    const spin = (s.index * 2.39996) % (Math.PI * 2);
    s.children.forEach((ci, i) => {
      const c = at(stars, ci);
      const t = (i + 0.5) / k;
      const cz = 1 - (1 - minCos) * (isRoot ? t : Math.sqrt(t));
      const rr = Math.sqrt(Math.max(0, 1 - cz * cz));
      const phi = i * GOLDEN + spin;
      const cx = rr * Math.cos(phi);
      const cy = rr * Math.sin(phi);
      const v: V = norm([
        d[0] * cz + u[0] * cx + w[0] * cy,
        d[1] * cz + u[1] * cx + w[1] * cy,
        d[2] * cz + u[2] * cx + w[2] * cy,
      ]);
      // A big leg stands further out, so its own branch has room to open.
      const dist = reach + 0.9 * Math.cbrt(c.size + 1);
      c.x = s.x + v[0] * dist;
      c.y = s.y + v[1] * dist * (isRoot ? 0.62 : 1);
      c.z = s.z + v[2] * dist;
      c.r = starRadius(c);
      dir[ci] = norm([c.x - s.x, c.y - s.y, c.z - s.z]);
    });
  }
}

/** Everyone in a branch (root included), as indexes. */
export function branchOf(stars: Star[], root: number): number[] {
  const out: number[] = [];
  const stack = [root];
  while (stack.length) {
    const i = stack.pop()!;
    out.push(i);
    stack.push(...at(stars, i).children);
  }
  return out;
}

/** From the viewer down to `i`. */
export function pathTo(stars: Star[], i: number): number[] {
  const out: number[] = [];
  let cur = i;
  let guard = 0;
  while (cur >= 0 && guard++ < 10_000) {
    out.push(cur);
    cur = at(stars, cur).parent;
  }
  return out.reverse();
}

/** Centre and size of a branch, to frame it with the camera. */
export function bounds(stars: Star[], ids: number[]): { cx: number; cy: number; cz: number; radius: number } {
  let cx = 0, cy = 0, cz = 0;
  for (const i of ids) { cx += at(stars, i).x; cy += at(stars, i).y; cz += at(stars, i).z; }
  cx /= ids.length; cy /= ids.length; cz /= ids.length;
  let radius = 0;
  for (const i of ids) radius = Math.max(radius, Math.hypot(at(stars, i).x - cx, at(stars, i).y - cy, at(stars, i).z - cz) + at(stars, i).r);
  return { cx, cy, cz, radius: Math.max(radius, 3) };
}

/** Colour by career level: from cool blue (no level) to gold (top levels). */
const LEVEL_COLORS = ["#5b6b8c", "#2f7bff", "#18b4ff", "#19d3c5", "#3ee08a", "#b3e341", "#ffc93c", "#ff9a3c", "#ff5fa2", "#c77dff"];

export function levelColor(level: number | null): string {
  return at(LEVEL_COLORS, level ? Math.min(level, LEVEL_COLORS.length - 1) : 0);
}

export function levelPalette(max: number): { level: number | null; color: string }[] {
  const out: { level: number | null; color: string }[] = [{ level: null, color: at(LEVEL_COLORS, 0) }];
  for (let l = 1; l <= Math.min(max, LEVEL_COLORS.length - 1); l++) out.push({ level: l, color: at(LEVEL_COLORS, l) });
  return out;
}

/** Stops of the automatic tour: the viewer, then the strongest legs. */
export function tourStops(stars: Star[], max = 7): number[] {
  if (!stars.length) return [];
  const legs = [...at(stars, 0).children].sort((a, b) => at(stars, b).bct - at(stars, a).bct || at(stars, b).size - at(stars, a).size);
  return [0, ...legs.slice(0, max - 1)];
}

/** Local search: everything is already here, so it is instant. */
export function searchStars(stars: Star[], q: string, limit = 8): number[] {
  const needle = q.trim().toLowerCase();
  if (needle.length < 2) return [];
  const hits: number[] = [];
  for (const s of stars) {
    if (`${s.name} ${s.code}`.toLowerCase().includes(needle)) hits.push(s.index);
  }
  return hits.sort((a, b) => at(stars, b).size - at(stars, a).size).slice(0, limit);
}
