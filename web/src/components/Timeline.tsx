"use client";

/**
 * Mission replay timeline: playback controls, a scrubber, and a tick for every
 * recorded event. Clicking a tick jumps to that moment.
 */

import { EVENT_COLOR, type ReplayEvent } from "@/lib/replay";

export function Timeline({
  frameCount,
  index,
  onSeek,
  playing,
  onTogglePlay,
  speed,
  onSpeed,
  events,
  compact = false,
}: {
  frameCount: number;
  index: number;
  onSeek: (i: number) => void;
  playing: boolean;
  onTogglePlay: () => void;
  speed: number;
  onSpeed: (s: number) => void;
  events: ReplayEvent[];
  compact?: boolean;
}) {
  const span = Math.max(frameCount - 1, 1);
  const ticks = events.filter((e) => e.kind !== "slip");
  return (
    <div className="flex items-center gap-3 border-t border-white/10 bg-[#0b0e14]/92 px-3 py-2">
      <button
        onClick={onTogglePlay}
        className="rounded-sm border border-white/15 px-3 py-1 font-mono text-[10px] tracking-[0.18em] text-slate-200 hover:bg-white/5"
      >
        {playing ? "PAUSE" : "PLAY"}
      </button>
      <button
        onClick={() => onSeek(Math.max(0, index - 1))}
        className="rounded-sm border border-white/10 px-1.5 py-1 font-mono text-[10px] text-slate-400 hover:text-slate-200"
        title="previous frame"
      >
        ◀
      </button>
      <button
        onClick={() => onSeek(Math.min(frameCount - 1, index + 1))}
        className="rounded-sm border border-white/10 px-1.5 py-1 font-mono text-[10px] text-slate-400 hover:text-slate-200"
        title="next frame"
      >
        ▶
      </button>
      <div className="relative flex-1">
        {!compact ? (
          <div className="relative mb-1 h-3">
            {ticks.map((e, k) => (
              <button
                key={`${e.frameIndex}-${e.kind}-${k}`}
                title={`T+${String(e.step).padStart(4, "0")}  ${e.text}`}
                onClick={() => onSeek(e.frameIndex)}
                className="absolute top-0 h-3 w-[3px] -translate-x-1/2 rounded-[1px] opacity-80 hover:opacity-100"
                style={{ left: `${(e.frameIndex / span) * 100}%`, background: EVENT_COLOR[e.tone] }}
              />
            ))}
          </div>
        ) : null}
        <input
          type="range"
          min={0}
          max={Math.max(frameCount - 1, 0)}
          value={index}
          onChange={(e) => onSeek(Number(e.target.value))}
          className="w-full accent-orange-500"
        />
      </div>
      <span className="font-mono text-[10px] tabular-nums text-slate-400">
        {String(index + 1).padStart(4, "0")}/{String(frameCount).padStart(4, "0")}
      </span>
      <select
        value={speed}
        onChange={(e) => onSpeed(Number(e.target.value))}
        className="rounded-sm border border-white/10 bg-black/40 px-2 py-1 font-mono text-[10px] text-slate-300"
      >
        <option value={320}>0.25x</option>
        <option value={180}>0.5x</option>
        <option value={90}>1x</option>
        <option value={40}>2x</option>
        <option value={14}>6x</option>
      </select>
    </div>
  );
}

export function ReplayLog({
  events,
  index,
  onSeek,
}: {
  events: ReplayEvent[];
  index: number;
  onSeek: (i: number) => void;
}) {
  const shown = events.filter((e) => e.frameIndex <= index);
  if (!shown.length) return <p className="font-mono text-xs text-slate-500">no events yet</p>;
  return (
    <ul className="max-h-[230px] space-y-[3px] overflow-y-auto pr-1">
      {shown
        .slice()
        .reverse()
        .map((e, k) => (
          <li key={`${e.frameIndex}-${e.kind}-${k}`}>
            <button
              onClick={() => onSeek(e.frameIndex)}
              className="flex w-full gap-2 text-left font-mono text-[10px] hover:bg-white/5"
              title="jump to this moment"
            >
              <span className="shrink-0 text-slate-600">T+{String(e.step).padStart(4, "0")}</span>
              <span style={{ color: EVENT_COLOR[e.tone] }}>{e.text}</span>
            </button>
          </li>
        ))}
    </ul>
  );
}
