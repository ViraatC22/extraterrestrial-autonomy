"use client";

/**
 * The 3D world: terrain, the rover, its driven trail, the route it currently
 * intends to take, science targets, and the lander.
 *
 * The visual grammar is deliberately minimal. Solid cyan is where the rover
 * has actually been; dashed violet is where it currently intends to go. When
 * the planner changes its mind, the violet line jumps while the cyan trail
 * does not - that contrast is the clearest way to show autonomy happening.
 */

import { Canvas } from "@react-three/fiber";
import { useCallback, useEffect, useRef as useReactRef, useState } from "react";
import { Billboard, Grid, Line, OrbitControls, Text } from "@react-three/drei";
import { useMemo } from "react";
import * as THREE from "three";

import { TerrainMesh, gridToWorld } from "./TerrainMesh";
import { UI } from "@/lib/palette";
import type { MissionSummary, TelemetryFrame, TerrainLayers, TerrainLayerName } from "@/lib/types";

/**
 * Labels are drawn in WebGL rather than with drei's <Html>.
 *
 * <Html> mounts a separate React root per label and tears it down on cleanup;
 * under React 19 that surfaces as "Attempted to synchronously unmount a root
 * while React was already rendering" on every frame where a marker changes.
 * Billboard + Text stays inside the canvas, so there are no extra roots and
 * the labels also occlude correctly against the terrain.
 */
function SceneLabel({
  position,
  text,
  color,
  size,
}: {
  position: [number, number, number];
  text: string;
  color: string;
  size: number;
}) {
  return (
    <Billboard position={position}>
      <Text
        fontSize={size}
        color={color}
        anchorX="center"
        anchorY="middle"
        outlineWidth={0.08}
        outlineColor="#05070a"
        letterSpacing={0.14}
      >
        {text}
      </Text>
    </Billboard>
  );
}

function Rover({ terrain, frame }: { terrain: TerrainLayers; frame: TelemetryFrame }) {
  const position = gridToWorld(terrain, frame.row, frame.col, 1.1);
  const stuck = !frame.moved && frame.reason === "slip_no_progress";
  return (
    <group position={position}>
      <mesh castShadow>
        <sphereGeometry args={[1.15, 20, 20]} />
        <meshStandardMaterial
          color={stuck ? UI.bad : UI.accent}
          emissive={stuck ? UI.bad : UI.accent}
          emissiveIntensity={stuck ? 0.9 : 0.35}
          roughness={0.4}
        />
      </mesh>
      {/* A vertical pin keeps the rover findable when the camera is low and
          the terrain is cluttered. */}
      <mesh position={[0, 3.2, 0]}>
        <cylinderGeometry args={[0.06, 0.06, 6, 6]} />
        <meshBasicMaterial color={stuck ? UI.bad : UI.accent} transparent opacity={0.55} />
      </mesh>
      <SceneLabel position={[0, 7.6, 0]} text="ROVER-01" color="#ffffff" size={1.8} />
    </group>
  );
}

function Marker({
  terrain,
  row,
  col,
  color,
  label,
  shape = "diamond",
}: {
  terrain: TerrainLayers;
  row: number;
  col: number;
  color: string;
  label?: string;
  shape?: "diamond" | "box";
}) {
  const position = gridToWorld(terrain, row, col, 1.4);
  return (
    <group position={position}>
      <mesh rotation={shape === "diamond" ? [0, Math.PI / 4, Math.PI / 4] : [0, 0, 0]}>
        {shape === "diamond" ? (
          <octahedronGeometry args={[1.05]} />
        ) : (
          <boxGeometry args={[1.8, 0.9, 1.8]} />
        )}
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={0.45}
          roughness={0.35}
        />
      </mesh>
      {label ? (
        <SceneLabel position={[0, 3.4, 0]} text={label} color="#c8d3e4" size={1.5} />
      ) : null}
    </group>
  );
}

function Route({
  terrain,
  cells,
  color,
  dashed,
  lift,
  width,
}: {
  terrain: TerrainLayers;
  cells: [number, number][];
  color: string;
  dashed?: boolean;
  lift: number;
  width: number;
}) {
  const points = useMemo(
    () =>
      cells.map(([row, col]) => {
        const [x, y, z] = gridToWorld(terrain, row, col, lift);
        return new THREE.Vector3(x, y, z);
      }),
    [terrain, cells, lift],
  );
  if (points.length < 2) return null;
  return (
    <Line
      points={points}
      color={color}
      lineWidth={width}
      dashed={dashed}
      dashSize={1.6}
      gapSize={1.2}
      transparent
      opacity={dashed ? 0.85 : 1}
    />
  );
}

export function MissionScene({
  terrain,
  summary,
  frame,
  trail,
  layer,
}: {
  terrain: TerrainLayers;
  summary: MissionSummary | null;
  frame: TelemetryFrame | null;
  trail: [number, number][];
  layer: TerrainLayerName;
}) {
  const visited = useMemo(() => new Set(trail.map(([r, c]) => `${r},${c}`)), [trail]);
  const [contextLost, setContextLost] = useState(false);
  // Bumping this remounts the <Canvas>, which builds a brand-new WebGL context.
  const [generation, setGeneration] = useState(0);
  const rebuildTimer = useReactRef<ReturnType<typeof setTimeout> | null>(null);

  // A browser can drop the WebGL context at any time - too many live contexts,
  // GPU pressure, a background tab. Calling preventDefault() asks the browser
  // to restore it, but restoration is not guaranteed and a canvas left holding
  // a dead context simply renders nothing, with no error and no explanation.
  // So if no `webglcontextrestored` arrives promptly, the canvas is rebuilt
  // from scratch rather than left blank.
  const handleCreated = useCallback(({ gl }: { gl: THREE.WebGLRenderer }) => {
    const canvas = gl.domElement;
    canvas.addEventListener("webglcontextlost", (event) => {
      event.preventDefault();
      setContextLost(true);
      if (rebuildTimer.current) clearTimeout(rebuildTimer.current);
      rebuildTimer.current = setTimeout(() => setGeneration((g) => g + 1), 1200);
    });
    canvas.addEventListener("webglcontextrestored", () => {
      if (rebuildTimer.current) clearTimeout(rebuildTimer.current);
      setContextLost(false);
    });
  }, []);

  // A rebuild produces a live context again.
  useEffect(() => {
    if (generation > 0) setContextLost(false);
  }, [generation]);

  useEffect(
    () => () => {
      if (rebuildTimer.current) clearTimeout(rebuildTimer.current);
    },
    [],
  );

  return (
    <>
    {contextLost ? (
      <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-[#07090d]/92">
        <p className="font-mono text-[11px] tracking-[0.2em] text-amber-300">
          GPU CONTEXT LOST — RESTORING
        </p>
      </div>
    ) : null}
    <Canvas
      key={generation}
      shadows
      camera={{ position: [70, 62, 78], fov: 42, far: 800 }}
      gl={{ antialias: true, powerPreference: "high-performance" }}
      onCreated={handleCreated}
      style={{ background: UI.bg }}
    >
      {/* Low sun angle: long shadows make relief legible, which matters more
          here than looking pretty. */}
      <hemisphereLight intensity={0.34} groundColor="#0a0d12" color="#c9d6ea" />
      <directionalLight
        position={[90, 58, 32]}
        intensity={2.1}
        castShadow
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
      />
      <ambientLight intensity={0.16} />

      <TerrainMesh terrain={terrain} layer={layer} />

      <Grid
        args={[140, 140]}
        cellSize={5}
        cellThickness={0.4}
        cellColor="#1d2835"
        sectionSize={25}
        sectionThickness={0.7}
        sectionColor="#27384a"
        position={[0, -0.25, 0]}
        infiniteGrid={false}
        fadeDistance={260}
      />

      {summary ? (
        <>
          <Marker
            terrain={terrain}
            row={summary.home[0]}
            col={summary.home[1]}
            color="#e9eef7"
            label="LANDER"
            shape="box"
          />
          {summary.targets.map((target) => {
            const reached = visited.has(`${target.row},${target.col}`);
            return (
              <Marker
                key={target.id}
                terrain={terrain}
                row={target.row}
                col={target.col}
                color={reached ? UI.good : UI.warn}
                label={`TGT ${String(target.id).padStart(2, "0")}`}
              />
            );
          })}
        </>
      ) : null}

      {frame?.planned_path?.length ? (
        <Route
          terrain={terrain}
          cells={frame.planned_path}
          color={UI.planned}
          dashed
          lift={1.0}
          width={2.2}
        />
      ) : null}

      {trail.length > 1 ? (
        <Route terrain={terrain} cells={trail} color={UI.route} lift={0.8} width={3.1} />
      ) : null}

      {frame ? <Rover terrain={terrain} frame={frame} /> : null}

      <OrbitControls
        enablePan
        enableDamping
        dampingFactor={0.08}
        minDistance={24}
        maxDistance={260}
        maxPolarAngle={Math.PI / 2.06}
        target={[0, 0, 0]}
      />
    </Canvas>
    </>
  );
}
