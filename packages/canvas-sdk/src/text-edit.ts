import { getDocumentVersion, type DesignDocument, type DesignOperation } from "../../design-ir/src/index";

export interface TextEditSnapshot {
  readonly node_id: string;
  readonly value: string;
  readonly composing: boolean;
  readonly dirty: boolean;
  readonly grapheme_count: number;
}

export function graphemeCount(value: string, locale = "zh"): number {
  if (typeof Intl.Segmenter === "function") {
    return [...new Intl.Segmenter(locale, { granularity: "grapheme" }).segment(value)].length;
  }
  return Array.from(value).length;
}

export function isTextInputTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || target.isContentEditable;
}

export function sanitizePastedText(value: string): string {
  return value.replace(/\r\n?/g, "\n").replace(/\u0000/g, "");
}

export class CanvasTextEditSession {
  readonly #nodeId: string;
  readonly #initial: string;
  #value: string;
  #composing = false;

  constructor(nodeId: string, initialValue: string) {
    this.#nodeId = nodeId;
    this.#initial = initialValue;
    this.#value = initialValue;
  }

  compositionStart(): void {
    this.#composing = true;
  }

  input(value: string): void {
    this.#value = value;
  }

  pastePlainText(value: string): void {
    this.#value += sanitizePastedText(value);
  }

  compositionEnd(value: string): void {
    this.#value = value;
    this.#composing = false;
  }

  cancel(): string {
    this.#value = this.#initial;
    this.#composing = false;
    return this.#initial;
  }

  snapshot(): TextEditSnapshot {
    return {
      node_id: this.#nodeId,
      value: this.#value,
      composing: this.#composing,
      dirty: this.#value !== this.#initial,
      grapheme_count: graphemeCount(this.#value),
    };
  }

  commitOperation(document: DesignDocument, operationId: string): DesignOperation | null {
    if (this.#composing || this.#value === this.#initial) return null;
    return {
      operation_id: operationId,
      type: "SET_TEXT",
      target_ids: [this.#nodeId],
      expected_document_version: getDocumentVersion(document),
      payload: { content: this.#value },
      reason: "canvas-text-edit",
    };
  }
}
