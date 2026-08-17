import type { OperationDescriptor } from "./types";

export type PastePolicy = "plain" | "normalized-rich";
export function graphemes(value: string): readonly string[] {
  if (typeof Intl !== "undefined" && "Segmenter" in Intl) {
    const SegmenterCtor = Intl.Segmenter;
    return [...new SegmenterCtor(undefined, { granularity: "grapheme" }).segment(value)].map((item) => item.segment);
  }
  return Array.from(value);
}
export function sanitizePastedText(value: string, policy: PastePolicy): string {
  const noScripts = value.replace(/<script[\s\S]*?<\/script>/gi, "").replace(/<style[\s\S]*?<\/style>/gi, "");
  if (policy === "plain") return noScripts.replace(/<br\s*\/?\s*>/gi, "\n").replace(/<[^>]+>/g, "").replace(/\r\n?/g, "\n");
  return noScripts.replace(/\son\w+\s*=\s*(["']).*?\1/gi, "").replace(/javascript:/gi, "");
}

export class TextEditSession {
  private valueValue: string;
  private composing = false;
  constructor(readonly nodeId: string, initialValue: string, readonly policy: PastePolicy = "plain") { this.valueValue = initialValue; }
  get value(): string { return this.valueValue; }
  get isComposing(): boolean { return this.composing; }
  compositionStart(): void { this.composing = true; }
  input(value: string): void { this.valueValue = value; }
  compositionEnd(value: string): void { this.valueValue = value; this.composing = false; }
  paste(value: string): string { const sanitized = sanitizePastedText(value, this.policy); this.valueValue += sanitized; return sanitized; }
  commit(): OperationDescriptor {
    if (this.composing) throw new Error("CANVAS_TEXT_COMPOSITION_ACTIVE");
    return { type: "SET_TEXT", targetIds: [this.nodeId], payload: { content: this.valueValue }, reason: "DOM text overlay commit" };
  }
}
