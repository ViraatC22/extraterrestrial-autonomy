"use client";

/**
 * Rover and lander, loaded from glTF models built by
 * scripts/build_vehicle_models.py (Blender, from code, in metres).
 *
 * Both are generic research platforms with no mission branding. They are
 * drawn to scale - one grid cell is one metre - so the rover is small against
 * the map, as it would be; a locator ring marks it in the overview cameras.
 *
 * What is data and what is illustration:
 *   - position is the simulator's cell; heading is the engine's recorded
 *     heading of the last move (TelemetryFrame.heading_deg)
 *   - pitch and roll follow the rendered surface under the vehicle
 *   - motion between cells, wheel rotation and surface dust are visual only;
 *     the simulator moves a point robot one cell per step
 */

import { useGLTF } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef, type RefObject } from "react";
import * as THREE from "three";

import { SUN_DIRECTION, SKY, cellStep, gridToWorld, heightAt } from "./TerrainMesh";
import { UI } from "@/lib/palette";
import type { TerrainLayers } from "@/lib/types";

export const ROVER_URL = "/models/rover.glb";
export const LANDER_URL = "/models/lander.glb";
useGLTF.preload(ROVER_URL);
useGLTF.preload(LANDER_URL);

/** Wheel radius in the rover model, metres (scripts/build_vehicle_models.py). */
const WHEEL_RADIUS_M = 0.25;

/** Engine heading (degrees clockwise from grid north, i.e. towards row 0) → yaw about +y. */
export function headingToYaw(headingDeg: number | null): number {
  return headingDeg === null ? Math.PI : Math.PI - (headingDeg * Math.PI) / 180;
}

/**
 * Orientation that sits a vehicle on the rendered surface at a yaw. `span`
 * is how far either side of the centre (in cells) the ground is sampled - a
 * wheelbase for the rover, a leg span for the lander.
 */
function terrainPose(t: TerrainLayers, row: number, col: number, yaw: number, span: number) {
  const step = cellStep(t);
  const dx = (heightAt(t, row, col + span) - heightAt(t, row, col - span)) / (2 * span * step);
  const dz = (heightAt(t, row + span, col) - heightAt(t, row - span, col)) / (2 * span * step);
  const normal = new THREE.Vector3(-dx, 1, -dz).normalize();
  const forward = new THREE.Vector3(Math.sin(yaw), 0, Math.cos(yaw));
  forward.sub(normal.clone().multiplyScalar(forward.dot(normal))).normalize();
  const right = new THREE.Vector3().crossVectors(normal, forward).normalize();
  const basis = new THREE.Matrix4().makeBasis(right, normal, forward);
  return new THREE.Quaternion().setFromRotationMatrix(basis);
}

/**
 * Reflections for the vehicles' metal and foil. Without an environment,
 * metallic surfaces render nearly black. This is a plain gradient of the
 * body's sky and ground colours plus the sun, applied to vehicles only - the
 * terrain keeps its own lighting.
 */
function useVehicleEnvironment(body: string): THREE.Texture {
  const gl = useThree((s) => s.gl);
  const env = useMemo(() => {
    const sky = SKY[body] ?? SKY.moon;
    const pmrem = new THREE.PMREMGenerator(gl);
    const scene = new THREE.Scene();
    const sphere = new THREE.SphereGeometry(10, 48, 24);
    const position = sphere.getAttribute("position");
    const colors = new Float32Array(position.count * 3);
    const top = new THREE.Color(sky.fog).multiplyScalar(0.6);
    const horizon = new THREE.Color(sky.ground).lerp(new THREE.Color("#8a8f99"), 0.35);
    const ground = new THREE.Color(sky.ground).multiplyScalar(1.4);
    const c = new THREE.Color();
    for (let i = 0; i < position.count; i += 1) {
      const y = position.getY(i) / 10;
      if (y >= 0) c.copy(horizon).lerp(top, Math.min(1, y * 1.6));
      else c.copy(horizon).lerp(ground, Math.min(1, -y * 3));
      colors.set([c.r, c.g, c.b], i * 3);
    }
    sphere.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    const shell = new THREE.Mesh(
      sphere,
      new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.BackSide }),
    );
    scene.add(shell);
    const sun = new THREE.Mesh(
      new THREE.SphereGeometry(0.7, 16, 8),
      new THREE.MeshBasicMaterial({ color: new THREE.Color(9, 8.6, 8) }),
    );
    sun.position.copy(SUN_DIRECTION).multiplyScalar(9);
    scene.add(sun);
    const texture = pmrem.fromScene(scene, 0.02).texture;
    pmrem.dispose();
    sphere.dispose();
    return texture;
  }, [gl, body]);
  useEffect(() => () => env.dispose(), [env]);
  return env;
}

/**
 * Regolith dust on up-facing surfaces: a colour, roughness and metalness
 * blend by how directly a surface faces the sky. Visual only.
 */
function addDust(material: THREE.MeshStandardMaterial, color: THREE.Color, amount: number) {
  material.onBeforeCompile = (shader) => {
    shader.uniforms.dustColor = { value: color };
    shader.uniforms.dustAmount = { value: amount };
    shader.fragmentShader = shader.fragmentShader
      .replace(
        "#include <common>",
        "#include <common>\nuniform vec3 dustColor;\nuniform float dustAmount;",
      )
      .replace(
        "#include <normal_fragment_maps>",
        `#include <normal_fragment_maps>
        vec3 upView = normalize((viewMatrix * vec4(0.0, 1.0, 0.0, 0.0)).xyz);
        float dust = dustAmount * smoothstep(0.2, 0.95, dot(normal, upView));
        diffuseColor.rgb = mix(diffuseColor.rgb, dustColor, dust);
        roughnessFactor = mix(roughnessFactor, 0.95, dust);
        metalnessFactor = mix(metalnessFactor, 0.0, dust);`,
      );
  };
  material.customProgramCacheKey = () => `dust-${amount.toFixed(2)}`;
}

const DUST: Record<string, string> = { mars: "#9a6446", moon: "#8d8b88" };

/** A private copy of a loaded model with shadows, reflections and dust. */
function useDressedModel(url: string, body: string, dustAmount: number) {
  const { scene } = useGLTF(url);
  const env = useVehicleEnvironment(body);
  const model = useMemo(() => {
    const copy = scene.clone(true);
    const dust = new THREE.Color(DUST[body] ?? DUST.moon);
    const cache = new Map<THREE.Material, THREE.MeshStandardMaterial>();
    copy.traverse((node) => {
      const mesh = node as THREE.Mesh;
      if (!mesh.isMesh) return;
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      const source = mesh.material as THREE.MeshStandardMaterial;
      let dressed = cache.get(source);
      if (!dressed) {
        dressed = source.clone();
        dressed.envMap = env;
        dressed.envMapIntensity = 0.9;
        if (!/lens/.test(source.name)) addDust(dressed, dust, dustAmount);
        cache.set(source, dressed);
      }
      mesh.material = dressed;
    });
    return copy;
  }, [scene, env, body, dustAmount]);
  return model;
}

export function RoverModel({
  terrain,
  row,
  col,
  headingDeg,
  stuck,
  roverRef,
  navcamRef,
}: {
  terrain: TerrainLayers;
  row: number;
  col: number;
  headingDeg: number | null;
  stuck: boolean;
  /** the drawn rover, for cameras and the locator (its smoothed pose) */
  roverRef: RefObject<THREE.Group | null>;
  /** the navigation camera's optical centre inside the model */
  navcamRef: RefObject<THREE.Object3D | null>;
}) {
  const model = useDressedModel(ROVER_URL, terrain.body, 0.32);
  const scale = cellStep(terrain); // metres → world units
  const target = useMemo(() => new THREE.Vector3(...gridToWorld(terrain, row, col, 0)), [terrain, row, col]);
  const pose = useMemo(
    () => terrainPose(terrain, row, col, headingToYaw(headingDeg), 0.8),
    [terrain, row, col, headingDeg],
  );
  const shownStuck = useRef<boolean | null>(null);

  useEffect(() => {
    navcamRef.current = model.getObjectByName("navcam") ?? null;
  }, [model, navcamRef]);

  useFrame((_, delta) => {
    const group = roverRef.current;
    if (!group) return;
    const wheels: THREE.Object3D[] = [];
    group.traverse((node) => {
      if (node.name.startsWith("wheel_")) wheels.push(node);
    });
    // A slip-stall is the one state worth flagging on the vehicle itself.
    if (shownStuck.current !== stuck) {
      for (const wheel of wheels) {
        wheel.traverse((child) => {
          const mesh = child as THREE.Mesh;
          if (!mesh.isMesh) return;
          const m = mesh.material as THREE.MeshStandardMaterial;
          m.emissive.set(stuck ? UI.bad : "#000000");
          m.emissiveIntensity = stuck ? 0.35 : 0;
        });
      }
      shownStuck.current = stuck;
    }
    const gap = group.position.distanceTo(target);
    // Seeks and new missions jump; ordinary steps glide.
    if (gap > scale * 3.5) {
      group.position.copy(target);
      group.quaternion.copy(pose);
      return;
    }
    const k = 1 - Math.exp(-delta * 10);
    const before = group.position.clone();
    group.position.lerp(target, k);
    group.quaternion.slerp(pose, k);
    const metres = before.distanceTo(group.position) / scale;
    for (const wheel of wheels) wheel.rotation.x += metres / WHEEL_RADIUS_M;
  });

  return (
    <group ref={roverRef} scale={scale}>
      <primitive object={model} />
    </group>
  );
}

/** Ring and pin marking the rover's position in the overview cameras. */
export function RoverLocator({
  roverRef,
  terrain,
  visible,
}: {
  roverRef: RefObject<THREE.Group | null>;
  terrain: TerrainLayers;
  visible: boolean;
}) {
  const locator = useRef<THREE.Group>(null);
  const scale = cellStep(terrain);
  useFrame(() => {
    const group = locator.current;
    const rover = roverRef.current;
    if (!group || !rover) return;
    group.position.copy(rover.position);
    group.visible = visible;
  });
  return (
    <group ref={locator} scale={scale}>
      <mesh position={[0, 0.08, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[1.75, 2.0, 48]} />
        <meshBasicMaterial color="#e9eef7" transparent opacity={0.75} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
      <mesh position={[0, 3.4, 0]}>
        <cylinderGeometry args={[0.03, 0.03, 2.6, 6]} />
        <meshBasicMaterial color="#e9eef7" transparent opacity={0.6} />
      </mesh>
    </group>
  );
}

/**
 * The model's "home" is the cell the rover parks on. The lander stands a few
 * metres away, ramp towards home, rather than on it - otherwise a rover at
 * home is drawn inside the lander. The offset is visual only; mission logic
 * uses the home cell.
 */
export const LANDER_OFFSET: [number, number] = [-3, -3];

export function landerCell(terrain: TerrainLayers, home: [number, number]): [number, number] {
  return [
    Math.min(Math.max(home[0] + LANDER_OFFSET[0], 0), terrain.size - 1),
    Math.min(Math.max(home[1] + LANDER_OFFSET[1], 0), terrain.size - 1),
  ];
}

export function LanderModel({ terrain, home }: { terrain: TerrainLayers; home: [number, number] }) {
  const model = useDressedModel(LANDER_URL, terrain.body, 0.4);
  const [r, c] = landerCell(terrain, home);
  const position = gridToWorld(terrain, r, c, 0);
  // ramp (model +z) points at the home cell
  const yaw = Math.atan2(home[1] - c, home[0] - r);
  const pose = useMemo(() => terrainPose(terrain, r, c, yaw, 2), [terrain, r, c, yaw]);
  return (
    <group position={position} quaternion={pose} scale={cellStep(terrain)}>
      <primitive object={model} />
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
      <lineBasicMaterial color={UI.route} transparent opacity={0.5} />
    </line>
  );
}
