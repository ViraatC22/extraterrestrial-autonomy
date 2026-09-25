"use client";

/**
 * Camera modes. Orbit is free; the others are driven each frame and eased so
 * that switching mode or following the rover never jumps.
 *
 *   orbit    free camera
 *   chase    behind and above the rover, following its heading
 *   top      straight down over the map - the scientific plan view
 *   pov      approximate mast-camera view from the rover
 *   planner  high oblique over the whole area, for candidate routes
 */

import { useFrame, useThree } from "@react-three/fiber";
import { useRef } from "react";
import * as THREE from "three";

import { WORLD_SIZE } from "./TerrainMesh";
import type { CameraMode } from "@/lib/types";

export function CameraRig({
  mode,
  rover,
  heading,
}: {
  mode: CameraMode;
  rover: [number, number, number] | null;
  heading: number;
}) {
  const { camera } = useThree();
  const target = useRef(new THREE.Vector3());
  const desired = useRef(new THREE.Vector3());

  useFrame((_, delta) => {
    if (mode === "orbit") return;
    const forward = new THREE.Vector3(Math.sin(heading), 0, Math.cos(heading));
    const focus = rover ? new THREE.Vector3(...rover) : new THREE.Vector3(0, 0, 0);

    if (mode === "chase" && rover) {
      desired.current.copy(focus).addScaledVector(forward, -16).add(new THREE.Vector3(0, 9, 0));
      target.current.copy(focus).addScaledVector(forward, 6);
    } else if (mode === "pov" && rover) {
      desired.current.copy(focus).addScaledVector(forward, 0.8).add(new THREE.Vector3(0, 3.2, 0));
      target.current.copy(focus).addScaledVector(forward, 30).add(new THREE.Vector3(0, -1.5, 0));
    } else if (mode === "top") {
      desired.current.set(0, WORLD_SIZE * 1.35, 0.01);
      target.current.set(0, 0, 0);
    } else {
      // planner, or chase/pov before a rover exists
      desired.current.set(0, WORLD_SIZE * 1.05, WORLD_SIZE * 0.62);
      target.current.set(0, 0, 0);
    }

    const k = 1 - Math.exp(-delta * 3.2);
    camera.position.lerp(desired.current, k);
    const look = new THREE.Vector3();
    camera.getWorldDirection(look);
    const wanted = target.current.clone().sub(camera.position).normalize();
    look.lerp(wanted, k).normalize();
    camera.lookAt(camera.position.clone().add(look));
  });

  return null;
}
