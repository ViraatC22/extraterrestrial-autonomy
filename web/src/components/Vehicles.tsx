"use client";

/**
 * Rover and lander models, built from primitives.
 *
 * Generic designs with no mission branding. The rover is drawn about two grid
 * cells long - roughly the size of a large planetary rover at this model's
 * 1 m cells, slightly enlarged so it stays findable from the overview camera.
 * It is posed on the terrain: heading from its last move, pitch and roll from
 * the local slope under its wheels.
 */

import { useMemo } from "react";
import * as THREE from "three";

import { cellStep, gridToWorld, heightAt } from "./TerrainMesh";
import { UI } from "@/lib/palette";
import type { TerrainLayers } from "@/lib/types";

const BODY = "#d9dde3";
const DARK = "#2b3038";
const FOIL = "#c89b3c";
const PANEL = "#1f2d4a";

/** Heading (radians about +y) from the previous distinct cell to this one. */
export function headingFromTrail(trail: [number, number][]): number {
  for (let i = trail.length - 1; i > 0; i -= 1) {
    const [r1, c1] = trail[i];
    const [r0, c0] = trail[i - 1];
    if (r1 !== r0 || c1 !== c0) return Math.atan2(c1 - c0, r1 - r0);
  }
  return 0;
}

/** Orientation that sits a vehicle on the local terrain at a heading. */
function terrainPose(t: TerrainLayers, row: number, col: number, heading: number) {
  const step = cellStep(t);
  const dx = (heightAt(t, row, col + 0.8) - heightAt(t, row, col - 0.8)) / (1.6 * step);
  const dz = (heightAt(t, row + 0.8, col) - heightAt(t, row - 0.8, col)) / (1.6 * step);
  const normal = new THREE.Vector3(-dx, 1, -dz).normalize();
  const forward = new THREE.Vector3(Math.sin(heading), 0, Math.cos(heading));
  forward.sub(normal.clone().multiplyScalar(forward.dot(normal))).normalize();
  const right = new THREE.Vector3().crossVectors(normal, forward).normalize();
  const basis = new THREE.Matrix4().makeBasis(right, normal, forward);
  return new THREE.Quaternion().setFromRotationMatrix(basis);
}

function Wheel({ position, alarm }: { position: [number, number, number]; alarm: boolean }) {
  return (
    <mesh position={position} rotation={[0, 0, Math.PI / 2]} castShadow>
      <cylinderGeometry args={[0.36, 0.36, 0.28, 18]} />
      <meshStandardMaterial
        color={alarm ? UI.bad : DARK}
        emissive={alarm ? UI.bad : "#000000"}
        emissiveIntensity={alarm ? 0.7 : 0}
        roughness={0.8}
      />
    </mesh>
  );
}

export function RoverModel({
  terrain,
  row,
  col,
  heading,
  stuck,
}: {
  terrain: TerrainLayers;
  row: number;
  col: number;
  heading: number;
  stuck: boolean;
}) {
  const position = gridToWorld(terrain, row, col, 0.55);
  const quaternion = useMemo(
    () => terrainPose(terrain, row, col, heading),
    [terrain, row, col, heading],
  );
  const scale = cellStep(terrain) * 1.05;
  const wheelX = 0.78;
  return (
    <group position={position} quaternion={quaternion} scale={scale}>
      {/* chassis */}
      <mesh position={[0, 0.42, 0]} castShadow>
        <boxGeometry args={[1.25, 0.34, 1.9]} />
        <meshStandardMaterial color={BODY} roughness={0.55} metalness={0.15} />
      </mesh>
      {/* solar deck */}
      <mesh position={[0, 0.62, -0.1]} castShadow>
        <boxGeometry args={[1.55, 0.05, 1.55]} />
        <meshStandardMaterial color={PANEL} roughness={0.3} metalness={0.4} />
      </mesh>
      {/* mast and camera head */}
      <mesh position={[0.32, 1.05, 0.72]} castShadow>
        <cylinderGeometry args={[0.05, 0.06, 0.85, 8]} />
        <meshStandardMaterial color={BODY} roughness={0.5} />
      </mesh>
      <mesh position={[0.32, 1.5, 0.76]} castShadow>
        <boxGeometry args={[0.42, 0.18, 0.2]} />
        <meshStandardMaterial color={DARK} roughness={0.4} />
      </mesh>
      {/* high-gain antenna */}
      <mesh position={[-0.42, 0.84, -0.55]} rotation={[-0.6, 0, 0]} castShadow>
        <cylinderGeometry args={[0.22, 0.22, 0.04, 16]} />
        <meshStandardMaterial color={BODY} roughness={0.5} />
      </mesh>
      {/* rocker-bogie wheels: three per side */}
      {[-0.72, 0, 0.72].map((z) => (
        <group key={z}>
          <Wheel position={[wheelX, 0.36, z]} alarm={stuck} />
          <Wheel position={[-wheelX, 0.36, z]} alarm={stuck} />
        </group>
      ))}
      <mesh position={[wheelX, 0.5, 0]}>
        <boxGeometry args={[0.08, 0.08, 1.5]} />
        <meshStandardMaterial color={DARK} />
      </mesh>
      <mesh position={[-wheelX, 0.5, 0]}>
        <boxGeometry args={[0.08, 0.08, 1.5]} />
        <meshStandardMaterial color={DARK} />
      </mesh>
    </group>
  );
}

/**
 * The model's "home" is the cell the rover parks on. The lander is drawn just
 * beside it rather than on it, otherwise a rover at home is hidden inside the
 * lander. The offset is visual only; the mission logic uses the home cell.
 */
export const LANDER_OFFSET: [number, number] = [-1.8, -1.8];

export function LanderModel({ terrain, row, col }: { terrain: TerrainLayers; row: number; col: number }) {
  const r = Math.min(Math.max(row + LANDER_OFFSET[0], 0), terrain.size - 1);
  const c = Math.min(Math.max(col + LANDER_OFFSET[1], 0), terrain.size - 1);
  const position = gridToWorld(terrain, r, c, 0);
  const scale = cellStep(terrain) * 1.25;
  const legs = [0, 1, 2, 3].map((i) => (i * Math.PI) / 2 + Math.PI / 4);
  return (
    <group position={position} scale={scale}>
      {legs.map((angle) => (
        <group key={angle} rotation={[0, angle, 0]}>
          <mesh position={[0, 0.6, 0.85]} rotation={[0.5, 0, 0]} castShadow>
            <cylinderGeometry args={[0.05, 0.05, 1.4, 6]} />
            <meshStandardMaterial color={BODY} roughness={0.5} metalness={0.3} />
          </mesh>
          <mesh position={[0, 0.06, 1.2]}>
            <cylinderGeometry args={[0.2, 0.24, 0.08, 12]} />
            <meshStandardMaterial color={BODY} roughness={0.6} />
          </mesh>
        </group>
      ))}
      {/* octagonal deck wrapped in foil */}
      <mesh position={[0, 1.15, 0]} castShadow>
        <cylinderGeometry args={[0.95, 1.05, 0.7, 8]} />
        <meshStandardMaterial color={FOIL} roughness={0.35} metalness={0.7} />
      </mesh>
      <mesh position={[0, 1.6, 0]} castShadow>
        <cylinderGeometry args={[0.7, 0.9, 0.22, 8]} />
        <meshStandardMaterial color={BODY} roughness={0.5} />
      </mesh>
      {/* solar wings */}
      {[-1, 1].map((side) => (
        <mesh key={side} position={[side * 1.75, 1.35, 0]} castShadow>
          <boxGeometry args={[1.5, 0.04, 0.8]} />
          <meshStandardMaterial color={PANEL} roughness={0.3} metalness={0.5} />
        </mesh>
      ))}
      {/* antenna dish */}
      <mesh position={[0, 2.05, 0]} rotation={[0.5, 0, 0]} castShadow>
        <sphereGeometry args={[0.38, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2.4]} />
        <meshStandardMaterial color={BODY} roughness={0.4} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}

/** Sensing footprint draped on the terrain around the rover. */
export function SensorFootprint({
  terrain,
  row,
  col,
  radius,
}: {
  terrain: TerrainLayers;
  row: number;
  col: number;
  radius: number;
}) {
  const points = useMemo(() => {
    const out: number[] = [];
    const segments = 96;
    for (let i = 0; i <= segments; i += 1) {
      const a = (i / segments) * Math.PI * 2;
      // clamped to the map: sensing does not extend past the simulated area
      const r = Math.min(Math.max(row + Math.cos(a) * radius, 0), terrain.size - 1);
      const c = Math.min(Math.max(col + Math.sin(a) * radius, 0), terrain.size - 1);
      out.push(...gridToWorld(terrain, r, c, 0.35));
    }
    return new Float32Array(out);
  }, [terrain, row, col, radius]);
  return (
    <line>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[points, 3]} />
      </bufferGeometry>
      <lineBasicMaterial color={UI.route} transparent opacity={0.7} />
    </line>
  );
}
