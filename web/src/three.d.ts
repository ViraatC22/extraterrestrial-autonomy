/**
 * React Three Fiber v9 with React 19 no longer augments the global JSX
 * namespace automatically: React 19 moved JSX under the `react` module, so the
 * three.js intrinsic elements (<mesh>, <meshStandardMaterial>, …) have to be
 * declared there explicitly or TypeScript rejects every element in a scene.
 */
import type { ThreeElements } from "@react-three/fiber";

declare module "react" {
  namespace JSX {
    // An empty extending interface is exactly the shape module augmentation
    // requires here - there are no members to add, only a supertype to merge
    // into the existing JSX namespace.
    // eslint-disable-next-line @typescript-eslint/no-empty-object-type
    interface IntrinsicElements extends ThreeElements {}
  }
}
