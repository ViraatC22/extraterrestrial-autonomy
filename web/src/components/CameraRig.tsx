"use client";

/**
 * Camera modes. Orbit is free; the others are driven each frame and eased so
 * that switching mode or following the rover never jumps.
 *
 *   orbit    free camera
 *   chase    spring arm behind and above the rover. The arm is shortened
 *            wherever the terrain or the lander would block it, so the view
 *            never ends up underground or inside the lander.
 *   top      straight down over the map - the scientific plan view
 *   navcam   the rover's mast camera: mounted at the camera's optical centre
 *            in the model, looking along the rover's heading, 10° down
 *   planner  high oblique over the whole area, for candidate routes
 *
 * Distances are in metres and converted with the grid scale (1 cell = 1 m).
 */

import { useFrame } from "@react-three/fiber";
import { useRef, type RefObject } from "react";
import * as THREE from "three";

import { WORLD_SIZE, cellStep, heightAt } from "./TerrainMesh";
import { NAVCAM_FOV_DEG } from "@/lib/camera";
import type { CameraMode, TerrainLayers } from "@/lib/types";

const DEFAULT_FOV_DEG = 42;

/** Chase arm, metres. */
const ARM_BACK = 7.5;
const ARM_UP = 3;
const PIVOT_UP = 1.6;
/** Keep the camera at least this far (metres) above the rendered surface. */
const CLEARANCE = 1.0;

export interface Obstacle {
  center: THREE.Vector3;
  radius: number;
}

/** Largest fraction of pivot→end that stays clear of terrain and obstacles. */
function clearFraction(
  terrain: TerrainLayers,
  pivot: THREE.Vector3,
  end: THREE.Vector3,
  obstacles: Obstacle[],
): number {
  const step = cellStep(terrain);
  const samples = 24;
  let fraction = 1;
  const p = new THREE.Vector3();
  for (let i = 1; i <= samples; i += 1) {
    const f = i / samples;
    p.lerpVectors(pivot, end, f);
    const row = (p.z + WORLD_SIZE / 2) / step;
    const col = (p.x + WORLD_SIZE / 2) / step;
    if (p.y < heightAt(terrain, row, col) + CLEARANCE * step) {
      fraction = Math.max(0.15, (i - 1) / samples);
      break;
    }
  }
  // ray-sphere test for each obstacle (the lander)
  const d = end.clone().sub(pivot);
  const len = d.length();
  d.normalize();
  for (const o of obstacles) {
    const m = pivot.clone().sub(o.center);
    const b = m.dot(d);
    const c = m.lengthSq() - o.radius * o.radius;
    if (c > 0 && b > 0) continue;
    const disc = b * b - c;
    if (disc < 0) continue;
    const t = -b - Math.sqrt(disc);
    if (t > 0 && t < len) fraction = Math.min(fraction, Math.max(0.15, (t / len) * 0.92));
  }
  return fraction;
}

export function CameraRig({
  mode,
  terrain,
  roverRef,
  navcamRef,
  obstacles,
}: {
  mode: CameraMode;
  terrain: TerrainLayers;
  roverRef: RefObject<THREE.Group | null>;
  navcamRef: RefObject<THREE.Object3D | null>;
  obstacles: Obstacle[];
}) {
  const target = useRef(new THREE.Vector3());
  const desired = useRef(new THREE.Vector3());
  const lensMode = useRef<CameraMode | null>(null);

  useFrame((state, delta) => {
    const camera = state.camera as THREE.PerspectiveCamera;
    if (lensMode.current !== mode) {
      camera.fov = mode === "navcam" ? NAVCAM_FOV_DEG : DEFAULT_FOV_DEG;
      camera.near = mode === "navcam" ? 0.05 : 0.3;
      camera.updateProjectionMatrix();
      lensMode.current = mode;
    }
    if (mode === "orbit") return;
    const metre = cellStep(terrain);
    const rover = roverRef.current;
    const focus = rover ? rover.position.clone() : new THREE.Vector3();
    const forward = new THREE.Vector3(0, 0, 1);
    if (rover) forward.applyQuaternion(rover.quaternion);
    forward.y = 0;
    if (forward.lengthSq() < 1e-6) forward.set(0, 0, 1);
    forward.normalize();

    const navcam = navcamRef.current;
    if (mode === "navcam" && rover && navcam) {
      // rigidly mounted: follow the (already smoothed) rover exactly
      navcam.getWorldPosition(camera.position);
      const look = new THREE.Vector3(0, -Math.sin(0.17), Math.cos(0.17)).applyQuaternion(rover.quaternion);
      camera.lookAt(camera.position.clone().add(look));
      return;
    }

    let k = 1 - Math.exp(-delta * 3.2);
    if (mode === "chase" && rover) {
      const pivot = focus.clone().add(new THREE.Vector3(0, PIVOT_UP * metre, 0));
      const end = pivot
        .clone()
        .addScaledVector(forward, -ARM_BACK * metre)
        .add(new THREE.Vector3(0, ARM_UP * metre, 0));
      const fraction = clearFraction(terrain, pivot, end, obstacles);
      desired.current.lerpVectors(pivot, end, fraction);
      target.current.copy(focus).addScaledVector(forward, 2.5 * metre).add(new THREE.Vector3(0, 0.2 * metre, 0));
      // pull in quickly when blocked, let out slowly when clear
      if (camera.position.distanceTo(pivot) > desired.current.distanceTo(pivot) + 0.1) {
        k = 1 - Math.exp(-delta * 12);
      }
    } else if (mode === "top") {
      desired.current.set(0, WORLD_SIZE * 1.35, 0.01);
      target.current.set(0, 0, 0);
    } else {
      // planner, or chase/navcam before a rover exists
      desired.current.set(0, WORLD_SIZE * 1.05, WORLD_SIZE * 0.62);
      target.current.set(0, 0, 0);
    }

    camera.position.lerp(desired.current, k);
    const look = new THREE.Vector3();
    camera.getWorldDirection(look);
    const wanted = target.current.clone().sub(camera.position).normalize();
    look.lerp(wanted, k).normalize();
    camera.lookAt(camera.position.clone().add(look));
  });

  return null;
}
