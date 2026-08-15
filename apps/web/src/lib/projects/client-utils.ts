import { LumiApiError } from "@/lib/app-shell/api-client";
import type {
  ProjectListFilters,
  ProjectSummary,
  StagedReference,
} from "./types";

export function projectListQueryKey(filters: ProjectListFilters): readonly (string | number | null)[] {
  return [
    "projects",
    filters.query,
    filters.status,
    filters.workspace_id,
    filters.brand_id,
    filters.sort,
    filters.cursor,
    filters.limit,
  ];
}

export function projectUiError(error: unknown): string {
  if (error instanceof LumiApiError) {
    switch (error.problem.code) {
      case "VERSION_CONFLICT":
        return "项目已在其他位置更新。已撤销本地改动，请刷新后重试。";
      case "PROJECT_NOT_FOUND":
        return "当前组织中找不到这个项目。";
      case "NETWORK_UNAVAILABLE":
        return "项目服务暂时不可用，请检查网络后重试。";
      case "HTTP_REQUEST_FAILED":
        return "Project Core 尚未连接到当前环境。界面已就绪，但不会假装写入成功。";
      case "UPLOAD_OBJECT_STORE_UNAVAILABLE":
      case "UPLOAD_OBJECT_PUT_FAILED":
        return "参考文件上传失败。项目本身不会因此被回滚或伪装为上传成功。";
      default:
        return `操作未完成（${error.problem.code}）。`;
    }
  }
  return error instanceof Error ? error.message : "操作未完成，请重试。";
}

export function mergeProject(
  projects: readonly ProjectSummary[],
  next: ProjectSummary,
): ProjectSummary[] {
  const found = projects.some((project) => project.id === next.id);
  if (!found) return [next, ...projects];
  return projects.map((project) => (project.id === next.id ? next : project));
}

export function parseBudgetMicrousd(value: string): bigint | null {
  const normalized = value.trim();
  if (!normalized) return null;
  if (!/^\d+(?:\.\d{1,2})?$/.test(normalized)) {
    throw new Error("预算请输入非负金额，最多两位小数。");
  }
  const [whole = "0", fraction = ""] = normalized.split(".");
  return BigInt(whole) * 1_000_000n + BigInt(fraction.padEnd(2, "0")) * 10_000n;
}

export function stageFiles(files: readonly File[]): StagedReference[] {
  return files.map((file) => ({
    client_id: crypto.randomUUID(),
    file,
    role: "other",
    ui_status: "LOCAL",
    progress: 0,
    asset_id: null,
    failure_code: null,
  }));
}

export function isAcceptedReference(file: File): boolean {
  const type = file.type.toLowerCase();
  const name = file.name.toLowerCase();
  return (
    type.startsWith("image/") ||
    type.startsWith("video/") ||
    type === "application/pdf" ||
    name.endsWith(".svg") ||
    name.endsWith(".ttf") ||
    name.endsWith(".otf") ||
    name.endsWith(".woff2")
  );
}

export const MAX_REFERENCE_BYTES = 100 * 1024 * 1024;
