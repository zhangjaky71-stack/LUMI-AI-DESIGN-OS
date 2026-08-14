import { isTextInputTarget } from "./text-edit";

export type CanvasKeyboardAction =
  | "select-tool"
  | "pan-tool"
  | "delete"
  | "copy"
  | "paste"
  | "undo"
  | "redo"
  | "nudge-left"
  | "nudge-right"
  | "nudge-up"
  | "nudge-down";

export interface KeyboardLikeEvent {
  readonly key: string;
  readonly code?: string;
  readonly metaKey?: boolean;
  readonly ctrlKey?: boolean;
  readonly shiftKey?: boolean;
  readonly altKey?: boolean;
  readonly target: EventTarget | null;
}

export function canvasKeyboardAction(event: KeyboardLikeEvent): CanvasKeyboardAction | null {
  if (isTextInputTarget(event.target)) return null;
  const command = Boolean(event.metaKey || event.ctrlKey);
  const key = event.key.toLowerCase();
  if (command && key === "c") return "copy";
  if (command && key === "v") return "paste";
  if (command && key === "z" && event.shiftKey) return "redo";
  if (command && key === "z") return "undo";
  if (key === "delete" || key === "backspace") return "delete";
  if (key === "v" && !command) return "select-tool";
  if (event.code === "Space" || key === " ") return "pan-tool";
  if (key === "arrowleft") return "nudge-left";
  if (key === "arrowright") return "nudge-right";
  if (key === "arrowup") return "nudge-up";
  if (key === "arrowdown") return "nudge-down";
  return null;
}

export function nudgeDelta(
  action: CanvasKeyboardAction,
  shiftKey = false,
): { readonly dx: number; readonly dy: number } | null {
  const amount = shiftKey ? 10 : 1;
  if (action === "nudge-left") return { dx: -amount, dy: 0 };
  if (action === "nudge-right") return { dx: amount, dy: 0 };
  if (action === "nudge-up") return { dx: 0, dy: -amount };
  if (action === "nudge-down") return { dx: 0, dy: amount };
  return null;
}
