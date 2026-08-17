export type FrameCallback = () => void;
export interface FrameScheduler { request(callback: FrameCallback): unknown; cancel(handle: unknown): void }
export class ImmediateFrameScheduler implements FrameScheduler { request(callback: FrameCallback): unknown { callback(); return 0; } cancel(): void {} }
export class RafFrameScheduler implements FrameScheduler {
  request(callback: FrameCallback): unknown { return requestAnimationFrame(callback); }
  cancel(handle: unknown): void { if (typeof handle === "number") cancelAnimationFrame(handle); }
}
