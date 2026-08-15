"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  isAcceptedReference,
  MAX_REFERENCE_BYTES,
  parseBudgetMicrousd,
  projectUiError,
  stageFiles,
} from "@/lib/projects/client-utils";
import type { ProjectsGateway } from "@/lib/projects/projects-gateway";
import type {
  ProjectDetail,
  ProjectSummary,
  ProjectsBootstrap,
  ReferenceRole,
  StagedReference,
} from "@/lib/projects/types";
import { REFERENCE_ROLE_LABELS } from "@/lib/projects/types";
import styles from "./projects.module.css";

const DELIVERABLES = ["主视觉", "社交媒体视觉", "产品图", "海报", "Banner", "品牌物料"] as const;

interface NewProjectDialogProps {
  readonly open: boolean;
  readonly organizationId: string;
  readonly bootstrap: ProjectsBootstrap;
  readonly gateway: ProjectsGateway;
  readonly onClose: () => void;
  readonly onCreated: (project: ProjectSummary) => void;
}

function updateStaged(
  items: readonly StagedReference[],
  clientId: string,
  patch: Partial<Omit<StagedReference, "client_id" | "file">>,
): StagedReference[] {
  return items.map((item) =>
    item.client_id === clientId ? { ...item, ...patch } : item,
  );
}

export function NewProjectDialog({
  open,
  organizationId,
  bootstrap,
  gateway,
  onClose,
  onCreated,
}: NewProjectDialogProps) {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [intent, setIntent] = useState("");
  const [name, setName] = useState("");
  const [brandId, setBrandId] = useState("");
  const [deliverables, setDeliverables] = useState<string[]>([]);
  const [locale, setLocale] = useState("zh-CN");
  const [qualityProfile, setQualityProfile] = useState("");
  const [budget, setBudget] = useState("");
  const [references, setReferences] = useState<StagedReference[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<ProjectDetail | null>(null);

  useEffect(() => {
    if (!open) return;
    setStep(1);
    setIntent("");
    setName("");
    setBrandId("");
    setDeliverables([]);
    setLocale("zh-CN");
    setQualityProfile("");
    setBudget("");
    setReferences([]);
    setError(null);
    setBusy(false);
    setCreated(null);
  }, [open, organizationId]);

  if (!open) return null;

  const appendFiles = (files: readonly File[]) => {
    const rejected = files.find(
      (file) => !isAcceptedReference(file) || file.size > MAX_REFERENCE_BYTES,
    );
    if (rejected) {
      setError(
        rejected.size > MAX_REFERENCE_BYTES
          ? `${rejected.name} 超过前端 100 MB 预检限制。服务端配额仍是最终权威。`
          : `${rejected.name} 不是当前支持的参考文件类型。`,
      );
      return;
    }
    setError(null);
    setReferences((current) => [...current, ...stageFiles(files)]);
  };

  const submit = async () => {
    if (!intent.trim()) {
      setError("只需要先告诉 LUMI 你想做什么。");
      setStep(1);
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const selectedBrand = bootstrap.brand_options.find(
        (brand) => brand.id === brandId,
      );
      const detail = await gateway.createProject(organizationId, {
        intent,
        name: name.trim() || null,
        brand_id: selectedBrand?.id ?? null,
        brand_name: selectedBrand?.name ?? null,
        deliverables,
        locale,
        quality_profile: qualityProfile || null,
        budget_microusd: parseBudgetMicrousd(budget),
      });
      setCreated(detail);
      onCreated(detail.summary);

      for (const item of references) {
        setReferences((current) =>
          updateStaged(current, item.client_id, {
            ui_status: "UPLOADING",
            progress: 1,
            failure_code: null,
          }),
        );
        try {
          const reference = await gateway.uploadReference(
            organizationId,
            {
              project_id: detail.summary.id,
              file: item.file,
              role: item.role,
              on_progress: (progress, status) => {
                setReferences((current) =>
                  updateStaged(current, item.client_id, {
                    ui_status: status,
                    progress,
                  }),
                );
              },
            },
          );
          setReferences((current) =>
            updateStaged(current, item.client_id, {
              asset_id: reference.asset_id,
              ui_status: reference.scan_status === "READY" ? "READY" : "FAILED",
              progress: 100,
              failure_code: reference.failure_code,
            }),
          );
        } catch (uploadError) {
          setReferences((current) =>
            updateStaged(current, item.client_id, {
              ui_status: "FAILED",
              progress: 100,
              failure_code: "UPLOAD_FAILED",
            }),
          );
          setError(projectUiError(uploadError));
        }
      }
      setStep(3);
    } catch (submitError) {
      setError(projectUiError(submitError));
    } finally {
      setBusy(false);
    }
  };

  const toggleDeliverable = (value: string) => {
    setDeliverables((current) =>
      current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value],
    );
  };

  return (
    <div className={styles.modalBackdrop}>
      <section
        className={styles.projectDialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-project-title"
      >
        <header className={styles.dialogHeader}>
          <div>
            <p className={styles.eyebrow}>NEW PROJECT</p>
            <h2 id="new-project-title">
              {step === 1 ? "你想做什么？" : step === 2 ? "补充一点上下文" : "项目已创建"}
            </h2>
          </div>
          <button
            type="button"
            className={styles.iconButton}
            onClick={onClose}
            aria-label="关闭新建项目"
            disabled={busy}
          >
            ×
          </button>
        </header>

        {step === 1 ? (
          <div className={styles.dialogBody}>
            <label className={styles.fieldLabel} htmlFor="project-intent">
              一句话描述
            </label>
            <textarea
              id="project-intent"
              autoFocus
              className={styles.intentInput}
              value={intent}
              onChange={(event) => setIntent(event.target.value)}
              placeholder="例如：为新品冷萃咖啡做一套高级极简的夏季发布视觉，主色黑白并带一点暖黄。"
              maxLength={4_000}
            />
            <div className={styles.fieldGrid}>
              <div>
                <label className={styles.fieldLabel} htmlFor="project-name">
                  项目名称 <span>可选</span>
                </label>
                <input
                  id="project-name"
                  className={styles.textInput}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="不填则从需求自动生成"
                  maxLength={120}
                />
              </div>
              <div>
                <span className={styles.fieldLabel}>参考文件 <span>可选</span></span>
                <button
                  type="button"
                  className={styles.dropZone}
                  onClick={() => fileInputRef.current?.click()}
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={(event) => {
                    event.preventDefault();
                    appendFiles([...event.dataTransfer.files]);
                  }}
                >
                  拖入或选择产品图、Logo、风格参考、PDF / 视频
                </button>
                <input
                  ref={fileInputRef}
                  className={styles.visuallyHidden}
                  type="file"
                  multiple
                  accept="image/*,video/*,application/pdf,.svg,.ttf,.otf,.woff2"
                  onChange={(event) => {
                    if (event.target.files) appendFiles([...event.target.files]);
                    event.target.value = "";
                  }}
                />
              </div>
            </div>

            {references.length > 0 ? (
              <div className={styles.referenceList} aria-label="待上传参考文件">
                {references.map((item) => (
                  <div key={item.client_id} className={styles.referenceRow}>
                    <div className={styles.referenceName}>
                      <strong>{item.file.name}</strong>
                      <span>{Math.max(1, Math.round(item.file.size / 1024))} KB</span>
                    </div>
                    <select
                      aria-label={`${item.file.name} 参考类型`}
                      value={item.role}
                      onChange={(event) =>
                        setReferences((current) =>
                          updateStaged(current, item.client_id, {
                            role: event.target.value as ReferenceRole,
                          }),
                        )
                      }
                    >
                      {(Object.entries(REFERENCE_ROLE_LABELS) as [ReferenceRole, string][]).map(
                        ([role, label]) => (
                          <option key={role} value={role}>{label}</option>
                        ),
                      )}
                    </select>
                    <button
                      type="button"
                      className={styles.textButton}
                      onClick={() =>
                        setReferences((current) =>
                          current.filter((reference) => reference.client_id !== item.client_id),
                        )
                      }
                    >
                      移除
                    </button>
                  </div>
                ))}
              </div>
            ) : null}

            {bootstrap.mode === "http" ? (
              <p className={styles.dependencyNote}>
                当前环境尚未连接 NODE-17/18 写端；提交时会以真实 API 结果为准，不会在浏览器伪造成功。
              </p>
            ) : null}
          </div>
        ) : null}

        {step === 2 ? (
          <div className={styles.dialogBody}>
            <div className={styles.fieldGrid}>
              <div>
                <label className={styles.fieldLabel} htmlFor="project-brand">Brand Kit</label>
                <select
                  id="project-brand"
                  className={styles.textInput}
                  value={brandId}
                  onChange={(event) => setBrandId(event.target.value)}
                >
                  <option value="">暂不绑定</option>
                  {bootstrap.brand_options.map((brand) => (
                    <option key={brand.id} value={brand.id}>{brand.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className={styles.fieldLabel} htmlFor="project-locale">语言 / Locale</label>
                <select
                  id="project-locale"
                  className={styles.textInput}
                  value={locale}
                  onChange={(event) => setLocale(event.target.value)}
                >
                  <option value="zh-CN">简体中文</option>
                  <option value="en-US">English (US)</option>
                  <option value="ja-JP">日本語</option>
                </select>
              </div>
            </div>

            <fieldset className={styles.fieldset}>
              <legend>计划交付物 <span>可选</span></legend>
              <div className={styles.choiceGrid}>
                {DELIVERABLES.map((item) => (
                  <label key={item} className={styles.choicePill} data-selected={deliverables.includes(item)}>
                    <input
                      type="checkbox"
                      checked={deliverables.includes(item)}
                      onChange={() => toggleDeliverable(item)}
                    />
                    {item}
                  </label>
                ))}
              </div>
            </fieldset>

            <details className={styles.advancedPanel}>
              <summary>高级设置</summary>
              <div className={styles.fieldGrid}>
                <div>
                  <label className={styles.fieldLabel} htmlFor="quality-profile">质量策略</label>
                  <select
                    id="quality-profile"
                    className={styles.textInput}
                    value={qualityProfile}
                    onChange={(event) => setQualityProfile(event.target.value)}
                  >
                    <option value="">使用组织默认</option>
                    <option value="BALANCED">Balanced</option>
                    <option value="QUALITY">Quality</option>
                    <option value="FAST">Fast</option>
                  </select>
                </div>
                <div>
                  <label className={styles.fieldLabel} htmlFor="project-budget">预算上限（USD）</label>
                  <input
                    id="project-budget"
                    inputMode="decimal"
                    className={styles.textInput}
                    value={budget}
                    onChange={(event) => setBudget(event.target.value)}
                    placeholder="例如 25.00"
                  />
                </div>
              </div>
            </details>
          </div>
        ) : null}

        {step === 3 && created ? (
          <div className={styles.dialogBody}>
            <div className={styles.successPanel}>
              <span className={styles.successMark} aria-hidden="true">✓</span>
              <div>
                <h3>{created.summary.name}</h3>
                <p>Project 已由真实 Gateway 确认创建。Structured Brief v{created.brief_version} 已建立。</p>
              </div>
            </div>
            {references.length > 0 ? (
              <div className={styles.uploadResults}>
                {references.map((item) => (
                  <div key={item.client_id} className={styles.uploadResultRow}>
                    <span>{item.file.name}</span>
                    <span data-status={item.ui_status}>
                      {item.ui_status === "READY"
                        ? "READY"
                        : item.ui_status === "FAILED"
                          ? `不可用 · ${item.failure_code ?? "UPLOAD_FAILED"}`
                          : `${item.ui_status} · ${item.progress}%`}
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}

        {error ? <p className={styles.formError} role="alert">{error}</p> : null}

        <footer className={styles.dialogFooter}>
          {step === 1 ? (
            <>
              <button type="button" className={styles.secondaryButton} onClick={onClose}>取消</button>
              <div className={styles.footerActions}>
                <button type="button" className={styles.secondaryButton} onClick={() => setStep(2)}>
                  下一步
                </button>
                <button type="button" className={styles.primaryButton} onClick={() => void submit()} disabled={busy}>
                  {busy ? "创建中…" : "直接开始"}
                </button>
              </div>
            </>
          ) : null}
          {step === 2 ? (
            <>
              <button type="button" className={styles.secondaryButton} onClick={() => setStep(1)} disabled={busy}>
                上一步
              </button>
              <button type="button" className={styles.primaryButton} onClick={() => void submit()} disabled={busy}>
                {busy ? "创建与上传中…" : "创建项目"}
              </button>
            </>
          ) : null}
          {step === 3 && created ? (
            <>
              <button type="button" className={styles.secondaryButton} onClick={onClose}>留在项目列表</button>
              <button
                type="button"
                className={styles.primaryButton}
                onClick={() => router.push(`/app/projects/${created.summary.id}`)}
              >
                进入项目
              </button>
            </>
          ) : null}
        </footer>
      </section>
    </div>
  );
}
