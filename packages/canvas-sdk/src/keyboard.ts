import type { KeyboardCommand } from "./types";

export interface KeyboardLikeEvent { readonly key: string; readonly code?: string; readonly ctrlKey?: boolean; readonly metaKey?: boolean; readonly shiftKey?: boolean; readonly target?: { readonly tagName?: string; readonly isContentEditable?: boolean } | null }
function editable(target: KeyboardLikeEvent["target"]): boolean { const tag = target?.tagName?.toUpperCase(); return target?.isContentEditable === true || tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT"; }
export function keyboardCommand(event: KeyboardLikeEvent): KeyboardCommand | null {
  if (editable(event.target)) return null;
  const mod = event.ctrlKey === true || event.metaKey === true; const key = event.key.toLowerCase();
  if (key === "v" && !mod) return "select-tool";
  if (event.code === "Space" || key === " ") return "pan-tool";
  if (key === "delete" || key === "backspace") return "delete";
  if (mod && key === "c") return "copy";
  if (mod && key === "v") return "paste";
  if (mod && key === "z" && event.shiftKey) return "redo";
  if (mod && key === "z") return "undo";
  if (key === "arrowleft") return "nudge-left"; if (key === "arrowright") return "nudge-right"; if (key === "arrowup") return "nudge-up"; if (key === "arrowdown") return "nudge-down";
  return null;
}
