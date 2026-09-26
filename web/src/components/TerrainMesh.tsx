"use client";

/**
 * The planetary surface, its surroundings, and its rocks.
 *
 * Everything that looks like data IS data: geometry is the simulator's
 * elevation, colour is either natural rendering of the true terrain class or
 * a selected scientific layer, and rocks sit only on cells the simulator
 * classes as rocky or rim talus, at a density set by their roughness.
 *
 * Two things are visual only and are labelled as such in the legend: fine
 * sub-cell surface texture, and the land beyond the simulated area, which
 * fades into haze so the map does not look like a floating tile. A faint
 * boundary line always marks where simulation stops.
 */

import { useEffect, useLayoutEffect, useMemo } from "react";
import * as THREE from "three";

import { LAYER_BY_KEY, layerUnit } from "@/lib/layers";
import { CLASS_COLORS, diverging, knowledgeColor, ramp } from "@/lib/palette";
import type { BeliefSnapshot, TerrainLayerName, TerrainLayers } from "@/lib/types";

export const WORLD_SIZE = 100;
export const HEIGHT_SCALE = 2.6;
const VERTICAL_WORLD = HEIGHT_SCALE * (WORLD_SIZE / 20);

export const cellStep = (t: TerrainLayers) => WORLD_SIZE / (t.size - 1);

/** How much the relief is stretched relative to true proportions. */
export function verticalExaggeration(t: TerrainLayers): number {
  const [lo, hi] = t.elevation_range;
  const metres = Math.max(hi - lo, 1e-6);
  return VERTICAL_WORLD / (metres * cellStep(t));
}

function normElevation(t: TerrainLayers, row: number, col: number): number {
  const [lo, hi] = t.elevation_range;
  return (t.elevation[row][col] - lo) / Math.max(hi - lo, 1e-6);
}

/** Bilinear height in world units at fractional grid coordinates. */
export function heightAt(t: TerrainLayers, row: number, col: number): number {
  const n = t.size;
  const r = Math.min(Math.max(row, 0), n - 1);
  const c = Math.min(Math.max(col, 0), n - 1);
  const r0 = Math.floor(r);
  const c0 = Math.floor(c);
  const r1 = Math.min(r0 + 1, n - 1);
  const c1 = Math.min(c0 + 1, n - 1);
  const fr = r - r0;
  const fc = c - c0;
  const h =
    normElevation(t, r0, c0) * (1 - fr) * (1 - fc) +
    normElevation(t, r0, c1) * (1 - fr) * fc +
    normElevation(t, r1, c0) * fr * (1 - fc) +
    normElevation(t, r1, c1) * fr * fc;
  return h * VERTICAL_WORLD;
}

/** Grid (row, col) → world (x, y, z), shared by every object in the scene. */
export function gridToWorld(
  terrain: TerrainLayers,
  row: number,
  col: number,
  lift = 0,
): [number, number, number] {
  const step = cellStep(terrain);
  return [col * step - WORLD_SIZE / 2, heightAt(terrain, row, col) + lift, row * step - WORLD_SIZE / 2];
}

/** World (x, z) → nearest grid cell, or null outside the simulated area. */
export function worldToGrid(terrain: TerrainLayers, x: number, z: number): [number, number] | null {
  const step = cellStep(terrain);
  const col = Math.round((x + WORLD_SIZE / 2) / step);
  const row = Math.round((z + WORLD_SIZE / 2) / step);
  if (row < 0 || col < 0 || row >= terrain.size || col >= terrain.size) return null;
  return [row, col];
}

/**
 * Light arrives from the -sun side of the simulator's lunar sun vector
 * (row 1.0, col 0.3): the lunar model shadows the crater-floor half on that
 * side, so placing the light there makes rendered shadows fall where the
 * model's permanently shadowed regions are. Mars has no sun direction in the
 * model; the same direction is used there as a visual choice.
 */
export const SUN_DIRECTION = new THREE.Vector3(-0.3, 0.42, -1.0).normalize();

/** Natural colour per true terrain class, per body. */
const SURFACE_PALETTE: Record<string, Record<number, [number, number, number]>> = {
  mars: {
    0: [0.56, 0.33, 0.21],
    1: [0.43, 0.27, 0.19],
    2: [0.74, 0.49, 0.3],
    3: [0.33, 0.22, 0.17],
    4: [0.5, 0.3, 0.2],
  },
  moon: {
    0: [0.5, 0.5, 0.49],
    1: [0.42, 0.42, 0.41],
    2: [0.6, 0.59, 0.57],
    3: [0.3, 0.3, 0.31],
    4: [0.46, 0.45, 0.44],
  },
};

export const SKY: Record<string, { fog: string; ground: string }> = {
  mars: { fog: "#241813", ground: "#3a2519" },
  moon: { fog: "#07080b", ground: "#1c1d20" },
};

/** Deterministic hash → [0,1), so the same seed always renders the same. */
function hash(a: number, b: number, seed: number): number {
  let h = (a * 374761393 + b * 668265263 + seed * 2147483647) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

function valueNoise(x: number, y: number, seed: number): number {
  const x0 = Math.floor(x);
  const y0 = Math.floor(y);
  const fx = x - x0;
  const fy = y - y0;
  const sx = fx * fx * (3 - 2 * fx);
  const sy = fy * fy * (3 - 2 * fy);
  const a = hash(x0, y0, seed);
  const b = hash(x0 + 1, y0, seed);
  const c = hash(x0, y0 + 1, seed);
  const d = hash(x0 + 1, y0 + 1, seed);
  return a + (b - a) * sx + (c - a) * sy + (a - b - c + d) * sx * sy;
}

function surfaceColor(t: TerrainLayers, row: number, col: number): [number, number, number] {
  const palette = SURFACE_PALETTE[t.body] ?? SURFACE_PALETTE.moon;
  const base = palette[t.terrain_class[row][col]] ?? [0.5, 0.5, 0.5];
  // Brightness varies with the model's own roughness and relief, plus a
  // little deterministic mottling so flat classes do not read as paint.
  const shade =
    0.84 +
    0.18 * normElevation(t, row, col) -
    0.12 * t.roughness[row][col] +
    0.1 * (valueNoise(col * 0.35, row * 0.35, t.seed) - 0.5);
  return [base[0] * shade, base[1] * shade, base[2] * shade];
}

export function layerColor(
  layer: TerrainLayerName,
  t: TerrainLayers,
  belief: BeliefSnapshot | null,
  row: number,
  col: number,
): [number, number, number] | null {
  const spec = LAYER_BY_KEY[layer];
  if (layer === "surface") return null;
  if (layer === "terrain_class") return CLASS_COLORS[t.terrain_class[row][col]] ?? [0.5, 0.5, 0.5];
  const v = layerUnit(spec, t, belief, row, col);
  if (v === null) return null;
  if (spec.ramp === "diverging") return diverging(v);
  if (spec.ramp === "knowledge") return knowledgeColor(v);
  return ramp(v);
}

let detailTexture: THREE.DataTexture | null = null;
/** Sub-cell grain for the lighting. Visual only; carries no data. */
function getDetailTexture(): THREE.DataTexture {
  if (detailTexture) return detailTexture;
  const size = 256;
  const data = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      const v =
        0.55 * valueNoise(x / 6, y / 6, 7) + 0.3 * valueNoise(x / 2.5, y / 2.5, 11) + 0.15 * valueNoise(x, y, 13);
      const i = (y * size + x) * 4;
      const byte = Math.round(v * 255);
      data[i] = byte;
      data[i + 1] = byte;
      data[i + 2] = byte;
      data[i + 3] = 255;
    }
  }
  const tex = new THREE.DataTexture(data, size, size);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(18, 18);
  tex.needsUpdate = true;
  detailTexture = tex;
  return tex;
}

export function TerrainMesh({
  terrain,
  layer,
  belief,
  opacity,
  onHover,
  onPin,
}: {
  terrain: TerrainLayers;
  layer: TerrainLayerName;
  belief: BeliefSnapshot | null;
  opacity: number;
  onHover?: (cell: [number, number] | null) => void;
  onPin?: (cell: [number, number]) => void;
}) {
  const geometry = useMemo(() => {
    const n = terrain.size;
    const geo = new THREE.PlaneGeometry(WORLD_SIZE, WORLD_SIZE, n - 1, n - 1);
    geo.rotateX(-Math.PI / 2);
    const position = geo.attributes.position as THREE.BufferAttribute;
    for (let i = 0; i < position.count; i += 1) {
      const col = i % n;
      const row = Math.floor(i / n);
      position.setY(i, normElevation(terrain, row, col) * VERTICAL_WORLD);
    }
    position.needsUpdate = true;
    geo.computeVertexNormals();
    geo.setAttribute("color", new THREE.BufferAttribute(new Float32Array(position.count * 3), 3));
    return geo;
  }, [terrain]);
  // built here rather than in JSX, so React Three Fiber will not free it
  useEffect(() => () => geometry.dispose(), [geometry]);

  // Colours change far more often than geometry (every belief snapshot), so
  // they are rewritten in place, after render, rather than rebuilding the mesh.
  useLayoutEffect(() => {
    const n = terrain.size;
    const colors = geometry.getAttribute("color") as THREE.BufferAttribute;
    for (let i = 0; i < colors.count; i += 1) {
      const col = i % n;
      const row = Math.floor(i / n);
      const natural = surfaceColor(terrain, row, col);
      const data = layerColor(layer, terrain, belief, row, col);
      let rgb = natural;
      if (data) {
        rgb = [
          natural[0] * (1 - opacity) + data[0] * opacity,
          natural[1] * (1 - opacity) + data[1] * opacity,
          natural[2] * (1 - opacity) + data[2] * opacity,
        ];
      }
      // True hazards are ground truth, so they are tinted only on views of the
      // world itself - never on views of what the rover believes, where they
      // would leak information the rover does not have.
      const showsTruth = !LAYER_BY_KEY[layer].needsBelief || layer === "true_slip";
      if (terrain.hazard[row][col] && layer !== "surface" && showsTruth) {
        rgb = [rgb[0] * 0.45 + 0.5, rgb[1] * 0.45 + 0.12, rgb[2] * 0.45 + 0.1];
      }
      colors.setXYZ(i, rgb[0], rgb[1], rgb[2]);
    }
    colors.needsUpdate = true;
  }, [geometry, terrain, layer, belief, opacity]);

  return (
    <mesh
      geometry={geometry}
      receiveShadow
      castShadow
      onPointerMove={(e) => {
        e.stopPropagation();
        onHover?.(worldToGrid(terrain, e.point.x, e.point.z));
      }}
      onPointerOut={() => onHover?.(null)}
      onClick={(e) => {
        // a drag to orbit the camera also ends in a click; only a still click pins
        if (e.delta > 4) return;
        e.stopPropagation();
        const cell = worldToGrid(terrain, e.point.x, e.point.z);
        if (cell) onPin?.(cell);
      }}
    >
      <meshStandardMaterial
        vertexColors
        roughness={0.96}
        metalness={0.0}
        bumpMap={getDetailTexture()}
        bumpScale={0.35}
      />
    </mesh>
  );
}

/**
 * Terrain beyond the simulated area. Heights continue smoothly from the map
 * edge and relax into low procedural relief; colour is desaturated and fog
 * takes it. None of it is simulated, and nothing here can be probed.
 */
export function Surroundings({ terrain }: { terrain: TerrainLayers }) {
  const geometry = useMemo(() => {
    const n = terrain.size;
    const factor = 5;
    const m = n * factor;
    const span = WORLD_SIZE * factor;
    const geo = new THREE.PlaneGeometry(span, span, m - 1, m - 1);
    geo.rotateX(-Math.PI / 2);
    const position = geo.attributes.position as THREE.BufferAttribute;
    const colors = new Float32Array(position.count * 3);
    const palette = SURFACE_PALETTE[terrain.body] ?? SURFACE_PALETTE.moon;
    const base = palette[0];
    const step = cellStep(terrain);
    const offset = (m - n) / 2;
    let meanH = 0;
    for (let r = 0; r < n; r += 1) for (let c = 0; c < n; c += 1) meanH += normElevation(terrain, r, c);
    meanH /= n * n;

    for (let i = 0; i < position.count; i += 1) {
      const gc = i % m;
      const gr = Math.floor(i / m);
      const r = gr - offset;
      const c = gc - offset;
      const inside = r >= 0 && c >= 0 && r <= n - 1 && c <= n - 1;
      const cr = Math.min(Math.max(r, 0), n - 1);
      const cc = Math.min(Math.max(c, 0), n - 1);
      const outside = Math.hypot(r - cr, c - cc);
      const edge = normElevation(terrain, Math.round(cr), Math.round(cc));
      const relief =
        meanH + 0.55 * (valueNoise(gc * 0.05, gr * 0.05, terrain.seed + 1) - 0.5) +
        0.18 * (valueNoise(gc * 0.18, gr * 0.18, terrain.seed + 2) - 0.5);
      const blend = 1 - Math.exp(-outside / 6);
      let h = (edge * (1 - blend) + relief * blend) * VERTICAL_WORLD;
      // sink under the simulated map so the two never z-fight
      if (inside && outside === 0) h -= 3.5;
      position.setX(i, (gc - (m - 1) / 2) * step);
      position.setZ(i, (gr - (m - 1) / 2) * step);
      position.setY(i, h);
      const shade = 0.66 + 0.2 * valueNoise(gc * 0.3, gr * 0.3, terrain.seed + 3);
      colors[i * 3] = base[0] * shade;
      colors[i * 3 + 1] = base[1] * shade;
      colors[i * 3 + 2] = base[2] * shade;
    }
    position.needsUpdate = true;
    geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    geo.computeVertexNormals();
    return geo;
  }, [terrain]);
  useEffect(() => () => geometry.dispose(), [geometry]);

  return (
    <mesh geometry={geometry} receiveShadow>
      <meshStandardMaterial vertexColors roughness={1} metalness={0} bumpMap={getDetailTexture()} bumpScale={0.25} />
    </mesh>
  );
}

/** Faint outline of where simulation stops, draped on the terrain edge. */
export function SimulatedBoundary({ terrain }: { terrain: TerrainLayers }) {
  const points = useMemo(() => {
    const n = terrain.size - 1;
    const edge: [number, number][] = [];
    for (let c = 0; c <= n; c += 1) edge.push([0, c]);
    for (let r = 0; r <= n; r += 1) edge.push([r, n]);
    for (let c = n; c >= 0; c -= 1) edge.push([n, c]);
    for (let r = n; r >= 0; r -= 1) edge.push([r, 0]);
    const flat: number[] = [];
    edge.forEach(([r, c]) => flat.push(...gridToWorld(terrain, r, c, 0.25)));
    return new Float32Array(flat);
  }, [terrain]);
  return (
    <line>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[points, 3]} />
      </bufferGeometry>
      <lineBasicMaterial color="#9fb3c8" transparent opacity={0.35} />
    </line>
  );
}

/**
 * Rocks on the cells the simulator classes as rocky (1) or rim talus (4),
 * with count per cell rising with that cell's roughness. Positions are a
 * deterministic hash of the cell, so a seed always looks the same.
 */
export function RockField({ terrain }: { terrain: TerrainLayers }) {
  const { matrices, count } = useMemo(() => {
    const out: THREE.Matrix4[] = [];
    const step = cellStep(terrain);
    const dummy = new THREE.Object3D();
    for (let r = 0; r < terrain.size; r += 1) {
      for (let c = 0; c < terrain.size; c += 1) {
        const cls = terrain.terrain_class[r][c];
        if (cls !== 1 && cls !== 4) continue;
        const rough = terrain.roughness[r][c];
        const n = Math.floor(rough * (cls === 4 ? 2.2 : 1.8) + hash(r, c, terrain.seed) * 0.9);
        for (let k = 0; k < n; k += 1) {
          const jr = r + (hash(r * 7 + k, c, terrain.seed) - 0.5);
          const jc = c + (hash(r, c * 7 + k, terrain.seed) - 0.5);
          const s = step * (0.12 + 0.22 * hash(r + k, c - k, terrain.seed));
          const [x, y, z] = gridToWorld(terrain, jr, jc, s * 0.25);
          dummy.position.set(x, y, z);
          dummy.rotation.set(
            hash(k, r, c) * Math.PI,
            hash(c, k, r) * Math.PI,
            hash(r, k, c) * Math.PI,
          );
          dummy.scale.set(s, s * (0.55 + 0.4 * hash(k, k, r)), s * (0.8 + 0.3 * hash(c, k, k)));
          dummy.updateMatrix();
          out.push(dummy.matrix.clone());
        }
      }
    }
    return { matrices: out, count: out.length };
  }, [terrain]);

  const color = terrain.body === "mars" ? "#7d4d36" : "#5d5d60";
  return (
    <instancedMesh
      key={`${terrain.body}-${terrain.seed}-${terrain.size}-${count}`}
      args={[undefined, undefined, Math.max(count, 1)]}
      castShadow
      receiveShadow
      ref={(mesh) => {
        if (!mesh) return;
        matrices.forEach((m, i) => mesh.setMatrixAt(i, m));
        mesh.count = count;
        mesh.instanceMatrix.needsUpdate = true;
      }}
    >
      <dodecahedronGeometry args={[1, 0]} />
      <meshStandardMaterial color={color} roughness={0.95} flatShading />
    </instancedMesh>
  );
}
