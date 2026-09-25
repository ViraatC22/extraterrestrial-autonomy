"use client";

/**
 * The 3D world: terrain, rocks, the rover and lander, the driven trail, the
 * route the rover currently intends to take, its sensing footprint, and - in
 * planner view - every candidate route it evaluated at the current decision.
 *
 * Visual grammar: solid cyan is where the rover has actually been; dashed
 * violet is where it currently intends to go. When the planner changes its
 * mind the violet line jumps while the cyan trail does not - that contrast is
 * the clearest way to show autonomy happening.
 */

import { Billboard, Line, OrbitControls, Text } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

import { CameraRig } from "./CameraRig";
import {
  RockField,
  SKY,
  SUN_DIRECTION,
  SimulatedBoundary,
  Surroundings,
  TerrainMesh,
  gridToWorld,
} from "./TerrainMesh";
import {
  LANDER_OFFSET,
  LanderModel,
  RoverModel,
  SensorFootprint,
  headingFromTrail,
} from "./Vehicles";
import { UI } from "@/lib/palette";
import type {
  BeliefSnapshot,
  CameraMode,
  Decision,
  MissionSummary,
  TelemetryFrame,
  TerrainLayerName,
  TerrainLayers,
} from "@/lib/types";

/**
 * Labels are drawn in WebGL rather than with drei's <Html>: <Html> mounts a
 * separate React root per label, which under React 19 surfaces as "Attempted
 * to synchronously unmount a root while React was already rendering".
 */
/** Labels are sized for the overview; close-in cameras shrink or hide them. */
const LABEL_SCALE: Record<CameraMode, number> = {
  orbit: 1,
  top: 1.15,
  planner: 1.1,
  chase: 0.38,
  pov: 0,
};
// Provided *inside* the <Canvas>: react-three-fiber renders with its own
// reconciler, which does not inherit context from outside the canvas.
const LabelScale = createContext(1);

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
  const labelScale = useContext(LabelScale);
  if (labelScale === 0) return null;
  size = size * labelScale;
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

function TargetBeacon({
  terrain,
  row,
  col,
  reached,
  label,
}: {
  terrain: TerrainLayers;
  row: number;
  col: number;
  reached: boolean;
  label: string;
}) {
  const [x, y, z] = gridToWorld(terrain, row, col, 0);
  const color = reached ? UI.good : UI.warn;
  return (
    <group position={[x, y, z]}>
      <mesh position={[0, 1.8, 0]}>
        <cylinderGeometry args={[0.07, 0.07, 3.6, 6]} />
        <meshBasicMaterial color={color} transparent opacity={0.7} />
      </mesh>
      <mesh position={[0, 3.8, 0]} rotation={[0, Math.PI / 4, Math.PI / 4]}>
        <octahedronGeometry args={[0.7]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.5} />
      </mesh>
      <mesh position={[0, 0.15, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[1.1, 1.35, 32]} />
        <meshBasicMaterial color={color} transparent opacity={0.8} side={THREE.DoubleSide} />
      </mesh>
      <SceneLabel position={[0, 6.2, 0]} text={label} color="#dfe6f0" size={1.3} />
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
  opacity = 1,
}: {
  terrain: TerrainLayers;
  cells: [number, number][];
  color: string;
  dashed?: boolean;
  lift: number;
  width: number;
  opacity?: number;
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
      gapSize={1.1}
      transparent
      opacity={opacity}
    />
  );
}

function CandidateRoutes({ terrain, decision }: { terrain: TerrainLayers; decision: Decision }) {
  return (
    <>
      {decision.candidates.map((candidate) => {
        if (!candidate.reachable || candidate.route.length < 2) return null;
        const color = candidate.selected ? UI.good : candidate.rejected ? UI.bad : "#8b98ab";
        const end = candidate.route[candidate.route.length - 1];
        const [x, y, z] = gridToWorld(terrain, end[0], end[1], 8.4);
        return (
          <group key={candidate.target_id}>
            <Route
              terrain={terrain}
              cells={candidate.route}
              color={color}
              dashed={!candidate.selected}
              lift={1.3}
              width={candidate.selected ? 3.4 : 2}
              opacity={candidate.selected ? 1 : 0.85}
            />
            <SceneLabel
              position={[x, y, z]}
              text={`P(fail) ${candidate.p_failure?.toFixed(3) ?? "—"}${candidate.selected ? "  ◀ CHOSEN" : candidate.rejected ? "  ✕ OVER BUDGET" : ""}`}
              color={color}
              size={1.05}
            />
          </group>
        );
      })}
    </>
  );
}

function ProbeMarker({ terrain, cell }: { terrain: TerrainLayers; cell: [number, number] }) {
  const [x, y, z] = gridToWorld(terrain, cell[0], cell[1], 0.3);
  return (
    <mesh position={[x, y, z]} rotation={[-Math.PI / 2, 0, 0]}>
      <ringGeometry args={[0.55, 0.85, 24]} />
      <meshBasicMaterial color="#ffffff" transparent opacity={0.9} side={THREE.DoubleSide} />
    </mesh>
  );
}

export function MissionScene({
  terrain,
  summary,
  frame,
  trail,
  layer,
  belief,
  opacity,
  cameraMode,
  decision,
  showCandidates,
  probeCell,
  onProbe,
}: {
  terrain: TerrainLayers;
  summary: MissionSummary | null;
  frame: TelemetryFrame | null;
  trail: [number, number][];
  layer: TerrainLayerName;
  belief: BeliefSnapshot | null;
  opacity: number;
  cameraMode: CameraMode;
  decision: Decision | null;
  showCandidates: boolean;
  probeCell: [number, number] | null;
  onProbe: (cell: [number, number] | null) => void;
}) {
  const visited = useMemo(() => new Set(trail.map(([r, c]) => `${r},${c}`)), [trail]);
  const heading = useMemo(() => headingFromTrail(trail), [trail]);
  const roverWorld = frame ? gridToWorld(terrain, frame.row, frame.col, 0) : null;
  const sky = SKY[terrain.body] ?? SKY.moon;

  const [contextLost, setContextLost] = useState(false);
  // Bumping this remounts the <Canvas>, which builds a brand-new WebGL context.
  const [generation, setGeneration] = useState(0);
  const rebuildTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // A browser can drop the WebGL context at any time. preventDefault() asks for
  // it back, but restoration is not guaranteed and a dead canvas renders
  // nothing, silently - so if it is not restored promptly, rebuild it.
  const handleCreated = useCallback(
    ({ gl }: { gl: THREE.WebGLRenderer }) => {
      const canvas = gl.domElement;
      canvas.addEventListener("webglcontextlost", (event) => {
        event.preventDefault();
        setContextLost(true);
        if (rebuildTimer.current) clearTimeout(rebuildTimer.current);
        rebuildTimer.current = setTimeout(() => {
          setGeneration((g) => g + 1);
          setContextLost(false);
        }, 1200);
      });
      canvas.addEventListener("webglcontextrestored", () => {
        if (rebuildTimer.current) clearTimeout(rebuildTimer.current);
        setContextLost(false);
      });
    },
    [rebuildTimer],
  );

  useEffect(() => {
    const timer = rebuildTimer;
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [rebuildTimer]);

  const sun = SUN_DIRECTION.clone().multiplyScalar(160);
  const stuck = Boolean(frame && !frame.moved && frame.reason === "slip_no_progress");

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
        camera={{ position: [70, 58, 82], fov: 42, near: 0.3, far: 1400 }}
        gl={{ antialias: true, powerPreference: "high-performance" }}
        onCreated={handleCreated}
        onPointerMissed={() => onProbe(null)}
      >
        <LabelScale.Provider value={LABEL_SCALE[cameraMode]}>
        <color attach="background" args={[sky.fog]} />
        <fog attach="fog" args={[sky.fog, 110, 380]} />

        <hemisphereLight intensity={0.3} groundColor={sky.ground} color="#c9d6ea" />
        <ambientLight intensity={0.1} />
        <directionalLight
          position={[sun.x, sun.y, sun.z]}
          intensity={2.4}
          castShadow
          shadow-mapSize-width={4096}
          shadow-mapSize-height={4096}
          shadow-camera-left={-75}
          shadow-camera-right={75}
          shadow-camera-top={75}
          shadow-camera-bottom={-75}
          shadow-camera-near={10}
          shadow-camera-far={400}
          shadow-bias={-0.0004}
        />

        <Surroundings terrain={terrain} />
        <TerrainMesh
          terrain={terrain}
          layer={layer}
          belief={belief}
          opacity={opacity}
          onProbe={onProbe}
        />
        <RockField terrain={terrain} />
        <SimulatedBoundary terrain={terrain} />

        {summary ? (
          <>
            <LanderModel terrain={terrain} row={summary.home[0]} col={summary.home[1]} />
            <SceneLabel
              position={gridToWorld(
                terrain,
                summary.home[0] + LANDER_OFFSET[0],
                summary.home[1] + LANDER_OFFSET[1],
                6.4,
              )}
              text="LANDER"
              color="#e9eef7"
              size={1.4}
            />
            {summary.targets.map((target) => (
              <TargetBeacon
                key={target.id}
                terrain={terrain}
                row={target.row}
                col={target.col}
                reached={visited.has(`${target.row},${target.col}`)}
                label={`TGT ${String(target.id).padStart(2, "0")}`}
              />
            ))}
          </>
        ) : null}

        {showCandidates && decision ? <CandidateRoutes terrain={terrain} decision={decision} /> : null}

        {!showCandidates && frame?.planned_path?.length ? (
          <Route
            terrain={terrain}
            cells={frame.planned_path}
            color={UI.planned}
            dashed
            lift={1.0}
            width={2.2}
            opacity={0.9}
          />
        ) : null}

        {trail.length > 1 ? (
          <Route terrain={terrain} cells={trail} color={UI.route} lift={0.5} width={3} />
        ) : null}

        {frame ? (
          <>
            <RoverModel terrain={terrain} row={frame.row} col={frame.col} heading={heading} stuck={stuck} />
            {frame.sensing_radius ? (
              <SensorFootprint
                terrain={terrain}
                row={frame.row}
                col={frame.col}
                radius={frame.sensing_radius}
              />
            ) : null}
          </>
        ) : null}

        {probeCell ? <ProbeMarker terrain={terrain} cell={probeCell} /> : null}

        <CameraRig mode={cameraMode} rover={roverWorld} heading={heading} />
        <OrbitControls
          enabled={cameraMode === "orbit"}
          enablePan
          enableDamping
          dampingFactor={0.08}
          minDistance={12}
          maxDistance={320}
          maxPolarAngle={Math.PI / 2.08}
          target={[0, 0, 0]}
        />
        </LabelScale.Provider>
      </Canvas>
    </>
  );
}
