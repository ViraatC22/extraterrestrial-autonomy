# EXONAUT mission control (frontend)

Next.js + React Three Fiber interface for the EXONAUT research engine.

This app holds **no simulation logic**. Every value it displays is produced by
the Python engine in `../src/exonaut/` and delivered over the FastAPI service,
so the interface cannot show a number the experiments did not produce.

## Running

The frontend needs the engine running first:

```bash
# terminal 1 - engine
source ~/.venvs/exonaut/bin/activate
python -m uvicorn exonaut.api:app --port 8000

# terminal 2 - interface
cd web && npm run dev      # http://localhost:3000
```

Point the app at a different engine with `NEXT_PUBLIC_EXONAUT_API`.

## A note on the npm scripts

This repository's directory name contains a colon (`Science Fair 26:27`). npm
puts `node_modules/.bin` on `PATH`, where `:` is the delimiter, so a bare
`next` cannot be resolved and `npm run dev` fails with
`sh: next: command not found`. The scripts therefore invoke the binaries
through `node` directly, which bypasses `PATH` entirely.

Renaming the directory to remove the colon would let the conventional scripts
work and is the cleaner long-term fix.

## Layout

```
src/lib/types.ts      wire types mirroring exonaut/api/models.py
src/lib/api.ts        typed client (REST + telemetry WebSocket)
src/lib/palette.ts    visual identity and terrain colour ramps
src/components/       TerrainMesh (3D surface), MissionScene, Panels (HUD)
src/app/page.tsx      MISSION CONTROL
```
