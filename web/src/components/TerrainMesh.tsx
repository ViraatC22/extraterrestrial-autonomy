"use client";

/**
 * The planetary surface.
 *
 * Elevation drives real vertex displacement rather than a texture, so craters
 * and rims are geometry the camera can look across. Colour encodes whichever
 * scientific layer is selected, and hazards are blended toward red on top of
 * that layer so they stay visible whatever else is being shown.
 */

import { useMemo, useRef } from "react";
import * as THREE from "three";

import { CLASS_COLORS, ramp } from "@/lib/palette";
import type { TerrainLayers, TerrainLayerName } from "@/lib/types";

export const WORLD_SIZE = 100;
export const HEIGHT_SCALE = 2.6;

/** Grid (row, col) → world (x, y, z), shared by every object in the scene. */
export function gridToWorld(
  terrain: TerrainLayers,
  row: number,
  col: number,
  lift = 0,
): [number, number, number] {
  const n = terrain.size;
  const step = WORLD_SIZE / (n - 1);
  const x = col * step - WORLD_SIZE / 2;
  const z = row * step - WORLD_SIZE / 2;
  const [low, high] = terrain.elevation_range;
  const span = Math.max(high - low, 1e-6);
  const normalized = (terrain.elevation[row][col] - low) / span;
  return [x, normalized * HEIGHT_SCALE * (WORLD_SIZE / 20) + lift, z];
}

function layerValue(
  terrain: TerrainLayers,
  layer: TerrainLayerName,
  row: number,
  col: number,
): number {
  switch (layer) {
    case "elevation": {
      const [low, high] = terrain.elevation_range;
      return (terrain.elevation[row][col] - low) / Math.max(high - low, 1e-6);
    }
    case "slope":
      return Math.min(1, terrain.slope[row][col] / 35);
    case "roughness":
      return terrain.roughness[row][col];
    case "illumination":
      return terrain.illumination[row][col];
    case "hazard":
      return terrain.hazard[row][col] ? 1 : 0;
    default:
      return 0;
  }
}

export function TerrainMesh({
  terrain,
  layer,
}: {
  terrain: TerrainLayers;
  layer: TerrainLayerName;
}) {
  const meshRef = useRef<THREE.Mesh>(null);

  const geometry = useMemo(() => {
    const n = terrain.size;
    const geo = new THREE.PlaneGeometry(WORLD_SIZE, WORLD_SIZE, n - 1, n - 1);
    geo.rotateX(-Math.PI / 2);

    const position = geo.attributes.position as THREE.BufferAttribute;
    const colors = new Float32Array(position.count * 3);
    const [low, high] = terrain.elevation_range;
    const span = Math.max(high - low, 1e-6);

    for (let i = 0; i < position.count; i += 1) {
      const col = i % n;
      const row = Math.floor(i / n);
      const normalized = (terrain.elevation[row][col] - low) / span;
      position.setY(i, normalized * HEIGHT_SCALE * (WORLD_SIZE / 20));

      let rgb: [number, number, number];
      if (layer === "terrain_class") {
        rgb = CLASS_COLORS[terrain.terrain_class[row][col]] ?? [0.5, 0.5, 0.5];
        // Shade by elevation so class colour does not flatten the relief.
        const shade = 0.72 + 0.4 * normalized;
        rgb = [rgb[0] * shade, rgb[1] * shade, rgb[2] * shade];
      } else {
        rgb = ramp(layerValue(terrain, layer, row, col));
      }

      if (terrain.hazard[row][col]) {
        // Blend toward the warning red rather than replacing the layer, so a
        // hazard cell still shows what kind of ground it is.
        rgb = [rgb[0] * 0.35 + 0.62, rgb[1] * 0.35 + 0.16, rgb[2] * 0.35 + 0.12];
      }

      colors[i * 3] = rgb[0];
      colors[i * 3 + 1] = rgb[1];
      colors[i * 3 + 2] = rgb[2];
    }

    geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    position.needsUpdate = true;
    geo.computeVertexNormals();
    return geo;
  }, [terrain, layer]);

  return (
    <mesh ref={meshRef} geometry={geometry} receiveShadow castShadow>
      <meshStandardMaterial vertexColors roughness={0.94} metalness={0.02} flatShading={false} />
    </mesh>
  );
}
