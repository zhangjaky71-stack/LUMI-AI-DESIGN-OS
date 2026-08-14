import { getDocumentVersion, type DesignNode, type DesignOperation, type JsonValue } from "../../design-ir/src/index";
import type { CriticSubject, DeterministicSignal, QualityEvidence, QualityViolation } from "./types";

function numeric(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function metadataNumber(node: DesignNode, key: string): number | null {
  return numeric(node.metadata?.[key]);
}

function content(node: DesignNode): string | null {
  return typeof node.content === "string" ? node.content : null;
}

function evidence(id: string, source: string, data: Readonly<Record<string, JsonValue>>): QualityEvidence {
  return { evidence_id: id, kind: "DETERMINISTIC", source, source_version: "1.0.0", confidence: 1, data };
}

function operation(id: string, type: DesignOperation["type"], target: string, version: number, payload: Readonly<Record<string, unknown>>, reason: string): DesignOperation {
  return { operation_id: id, type, target_ids: [target], expected_document_version: version, payload, reason };
}

function hexRgb(value: unknown): readonly [number, number, number] | null {
  if (typeof value !== "string") return null;
  const match = /^#([0-9a-f]{6})$/i.exec(value.trim());
  if (!match) return null;
  const hex = match[1]!;
  return [Number.parseInt(hex.slice(0, 2), 16), Number.parseInt(hex.slice(2, 4), 16), Number.parseInt(hex.slice(4, 6), 16)];
}

function luminance(rgb: readonly [number, number, number]): number {
  const values = rgb.map((v) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * values[0]! + 0.7152 * values[1]! + 0.0722 * values[2]!;
}

function contrastRatio(fg: readonly [number, number, number], bg: readonly [number, number, number]): number {
  const a = luminance(fg);
  const b = luminance(bg);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

export function evaluateDeterministicSignals(subject: CriticSubject): readonly DeterministicSignal[] {
  const document = subject.design_document;
  const version = getDocumentVersion(document);
  const signals: DeterministicSignal[] = [];
  const textNodes = Object.values(document.nodes).filter((node) => node.kind === "TEXT" && node.visible !== false);

  const overflowEvidence: QualityEvidence[] = [];
  const overflowViolations: QualityViolation[] = [];
  const overflowRepairs: DesignOperation[] = [];
  for (const node of textNodes) {
    const width = numeric(node.transform?.width);
    const height = numeric(node.transform?.height);
    const measuredWidth = metadataNumber(node, "measured_width");
    const measuredHeight = metadataNumber(node, "measured_height");
    if (width === null || height === null || measuredWidth === null || measuredHeight === null) continue;
    if (measuredWidth <= width + 0.25 && measuredHeight <= height + 0.25) continue;
    const id = `det:typography-overflow:${node.id}`;
    overflowEvidence.push(evidence(id, "design-ir.text-metrics", { node_id: node.id, width, height, measured_width: measuredWidth, measured_height: measuredHeight }));
    overflowViolations.push({ violation_id: `violation:${id}`, dimension: "TYPOGRAPHY_READABILITY", severity: "MAJOR", reason_code: "TEXT_OVERFLOW", message: `Text node ${node.id} exceeds its layout box`, target_id: node.id, evidence_ids: [id], repairable: true });
    overflowRepairs.push(operation(`quality:resize:${node.id}:${version}`, "RESIZE_NODE", node.id, version, { width: Math.max(width, measuredWidth), height: Math.max(height, measuredHeight) }, "Expand text box to measured content bounds"));
  }
  if (overflowEvidence.length) {
    signals.push({ dimension: "TYPOGRAPHY_READABILITY", score: Math.max(0, 100 - overflowEvidence.length * 20), confidence: 1, severity: "MAJOR", hard_fail: false, reason_codes: ["TEXT_OVERFLOW"], evidence: overflowEvidence, violations: overflowViolations, repair_operations: overflowRepairs });
  }

  const geometryEvidence: QualityEvidence[] = [];
  const geometryViolations: QualityViolation[] = [];
  const geometryRepairs: DesignOperation[] = [];
  for (const node of Object.values(document.nodes)) {
    if (!node.parent_id || node.visible === false) continue;
    const parent = document.nodes[node.parent_id];
    if (!parent) continue;
    const x = numeric(node.transform?.x);
    const y = numeric(node.transform?.y);
    const width = numeric(node.transform?.width);
    const height = numeric(node.transform?.height);
    const parentWidth = numeric(parent.transform?.width);
    const parentHeight = numeric(parent.transform?.height);
    if ([x, y, width, height, parentWidth, parentHeight].some((value) => value === null)) continue;
    const outside = x! < -0.25 || y! < -0.25 || x! + width! > parentWidth! + 0.25 || y! + height! > parentHeight! + 0.25;
    if (!outside) continue;
    const id = `det:bounds:${node.id}`;
    geometryEvidence.push(evidence(id, "design-ir.geometry", { node_id: node.id, parent_id: parent.id, x: x!, y: y!, width: width!, height: height!, parent_width: parentWidth!, parent_height: parentHeight! }));
    geometryViolations.push({ violation_id: `violation:${id}`, dimension: "ALIGNMENT_SPACING", severity: "MAJOR", reason_code: "NODE_OUTSIDE_PARENT", message: `Node ${node.id} extends outside parent ${parent.id}`, target_id: node.id, evidence_ids: [id], repairable: true });
    geometryRepairs.push(operation(`quality:move:${node.id}:${version}`, "MOVE_NODE", node.id, version, { x: Math.min(Math.max(0, x!), Math.max(0, parentWidth! - width!)), y: Math.min(Math.max(0, y!), Math.max(0, parentHeight! - height!)) }, "Clamp node inside parent bounds"));
  }
  if (geometryEvidence.length) signals.push({ dimension: "ALIGNMENT_SPACING", score: Math.max(0, 100 - geometryEvidence.length * 15), confidence: 1, severity: "MAJOR", hard_fail: false, reason_codes: ["NODE_OUTSIDE_PARENT"], evidence: geometryEvidence, violations: geometryViolations, repair_operations: geometryRepairs });

  const contrastEvidence: QualityEvidence[] = [];
  const contrastViolations: QualityViolation[] = [];
  for (const node of textNodes) {
    const fg = hexRgb(node.metadata?.foreground_color);
    const bg = hexRgb(node.metadata?.background_color);
    if (!fg || !bg) continue;
    const ratio = contrastRatio(fg, bg);
    const id = `det:contrast:${node.id}`;
    contrastEvidence.push(evidence(id, "design-ir.color-metadata", { node_id: node.id, ratio }));
    if (ratio < 3) contrastViolations.push({ violation_id: `violation:${id}`, dimension: "CONTRAST", severity: "MAJOR", reason_code: "LOW_TEXT_CONTRAST", message: `Text node ${node.id} contrast ratio ${ratio.toFixed(2)} is below the configured design floor`, target_id: node.id, evidence_ids: [id], repairable: false });
  }
  if (contrastEvidence.length) {
    const minimum = Math.min(...contrastEvidence.map((item) => numeric(item.data?.ratio) ?? 0));
    signals.push({ dimension: "CONTRAST", score: Math.min(100, Math.round((minimum / 4.5) * 100)), confidence: 1, severity: contrastViolations.length ? "MAJOR" : "ADVISORY", hard_fail: false, reason_codes: contrastViolations.length ? ["LOW_TEXT_CONTRAST"] : [], evidence: contrastEvidence, violations: contrastViolations });
  }

  if (subject.expected_text?.length) {
    const actual = textNodes.map(content).filter((value): value is string => value !== null);
    const missing = subject.expected_text.filter((expected) => !actual.includes(expected));
    const ev = evidence("det:text-accuracy", "design-ir.text", { expected_count: subject.expected_text.length, actual_count: actual.length, missing_count: missing.length });
    const violations = missing.map((value, index) => ({ violation_id: `violation:text-missing:${index}`, dimension: "TEXT_ACCURACY" as const, severity: "MAJOR" as const, reason_code: "EXPECTED_TEXT_MISSING", message: `Expected text is missing: ${value}`, evidence_ids: [ev.evidence_id], repairable: textNodes.length === 1 && subject.expected_text!.length === 1 }));
    const repairs = missing.length === 1 && textNodes.length === 1 && subject.expected_text.length === 1
      ? [operation(`quality:set-text:${textNodes[0]!.id}:${version}`, "SET_TEXT", textNodes[0]!.id, version, { content: subject.expected_text[0]! }, "Restore exact expected text")]
      : [];
    signals.push({ dimension: "TEXT_ACCURACY", score: Math.max(0, Math.round(((subject.expected_text.length - missing.length) / subject.expected_text.length) * 100)), confidence: 1, severity: missing.length ? "MAJOR" : "ADVISORY", hard_fail: false, reason_codes: missing.length ? ["EXPECTED_TEXT_MISSING"] : [], evidence: [ev], violations, repair_operations: repairs });
  }

  const minWidth = numeric(subject.metadata?.minimum_export_width);
  const minHeight = numeric(subject.metadata?.minimum_export_height);
  if (minWidth !== null || minHeight !== null) {
    const widthOk = minWidth === null || (subject.width !== undefined && subject.width >= minWidth);
    const heightOk = minHeight === null || (subject.height !== undefined && subject.height >= minHeight);
    const ev = evidence("det:resolution", "artifact.metadata", { width: subject.width ?? 0, height: subject.height ?? 0, minimum_width: minWidth ?? 0, minimum_height: minHeight ?? 0 });
    signals.push({ dimension: "RESOLUTION_EXPORT_READINESS", score: widthOk && heightOk ? 100 : 0, confidence: subject.width !== undefined && subject.height !== undefined ? 1 : 0, severity: widthOk && heightOk ? "ADVISORY" : "HARD", hard_fail: !widthOk || !heightOk, reason_codes: widthOk && heightOk ? [] : ["EXPORT_RESOLUTION_TOO_LOW"], evidence: [ev], violations: widthOk && heightOk ? [] : [{ violation_id: "violation:resolution", dimension: "RESOLUTION_EXPORT_READINESS", severity: "HARD", reason_code: "EXPORT_RESOLUTION_TOO_LOW", message: "Rendered artifact does not meet the required export resolution", evidence_ids: [ev.evidence_id], repairable: false }] });
  }

  return signals;
}
