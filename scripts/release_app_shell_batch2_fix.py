from __future__ import annotations

from pathlib import Path


def replace(path: str, old: str, new: str, *, count: int = 1) -> None:
    target = Path(path)
    source = target.read_text(encoding="utf-8")
    found = source.count(old)
    if found < count:
        raise SystemExit(
            f"expected App Shell target missing: {path}: wanted {count}, found {found}: {old!r}"
        )
    target.write_text(source.replace(old, new, count), encoding="utf-8")


ai = "apps/web/src/components/ai-workspace/ai-workspace.tsx"
replace(
    ai,
    "  useEffect(() => {\n"
    "    let cancelled = false;\n"
    "    setLoading(true);\n"
    "    setError(null);\n"
    "    void refreshCanonical()\n"
    "      .catch((loadError) => {\n"
    "        if (!cancelled) setError(uiError(loadError));\n"
    "      })\n"
    "      .finally(() => {\n"
    "        if (!cancelled) setLoading(false);\n"
    "      });\n"
    "    return () => {\n"
    "      cancelled = true;\n"
    "      streamAbortRef.current?.abort();\n"
    "    };\n"
    "  }, [refreshCanonical]);\n",
    "  useEffect(() => {\n"
    "    let cancelled = false;\n"
    "    queueMicrotask(() => {\n"
    "      if (cancelled) return;\n"
    "      setLoading(true);\n"
    "      setError(null);\n"
    "      void refreshCanonical()\n"
    "        .catch((loadError) => {\n"
    "          if (!cancelled) setError(uiError(loadError));\n"
    "        })\n"
    "        .finally(() => {\n"
    "          if (!cancelled) setLoading(false);\n"
    "        });\n"
    "    });\n"
    "    return () => {\n"
    "      cancelled = true;\n"
    "      streamAbortRef.current?.abort();\n"
    "    };\n"
    "  }, [refreshCanonical]);\n",
)
replace(
    ai,
    "  useEffect(() => {\n"
    "    if (!focusNodeId || focusAppliedRef.current || !canvasEditorState) return;\n"
    "    if (!containsLayer(canvasEditorState.layers, focusNodeId)) {\n"
    "      setError(`Brand compliance 指向的 Canvas node 不存在：${focusNodeId}`);\n"
    "      focusAppliedRef.current = true;\n"
    "      return;\n"
    "    }\n"
    "    canvasEditorRef.current?.select([focusNodeId], focusNodeId);\n"
    "    canvasEditorRef.current?.fitSelection();\n"
    "    setMobilePanel(\"canvas\");\n"
    "    focusAppliedRef.current = true;\n"
    "  }, [canvasEditorState, focusNodeId]);\n",
    "  useEffect(() => {\n"
    "    if (!focusNodeId || focusAppliedRef.current || !canvasEditorState) return;\n"
    "    if (!containsLayer(canvasEditorState.layers, focusNodeId)) {\n"
    "      focusAppliedRef.current = true;\n"
    "      queueMicrotask(() => {\n"
    "        setError(`Brand compliance 指向的 Canvas node 不存在：${focusNodeId}`);\n"
    "      });\n"
    "      return;\n"
    "    }\n"
    "    canvasEditorRef.current?.select([focusNodeId], focusNodeId);\n"
    "    canvasEditorRef.current?.fitSelection();\n"
    "    focusAppliedRef.current = true;\n"
    "    queueMicrotask(() => {\n"
    "      setMobilePanel(\"canvas\");\n"
    "    });\n"
    "  }, [canvasEditorState, focusNodeId]);\n",
)

brand = "apps/web/src/components/brand-kit/brand-kit.tsx"
replace(brand, "  BrandVisualAsset,\n", "")
replace(
    brand,
    "  useEffect(() => {\n"
    "    let cancelled = false;\n"
    "    setLoading(true);\n"
    "    setError(null);\n"
    "    void load()\n"
    "      .catch((loadError) => {\n"
    "        if (!cancelled) setError(uiError(loadError));\n"
    "      })\n"
    "      .finally(() => {\n"
    "        if (!cancelled) setLoading(false);\n"
    "      });\n"
    "    return () => { cancelled = true; };\n"
    "  }, [load]);\n",
    "  useEffect(() => {\n"
    "    let cancelled = false;\n"
    "    queueMicrotask(() => {\n"
    "      if (cancelled) return;\n"
    "      setLoading(true);\n"
    "      setError(null);\n"
    "      void load()\n"
    "        .catch((loadError) => {\n"
    "          if (!cancelled) setError(uiError(loadError));\n"
    "        })\n"
    "        .finally(() => {\n"
    "          if (!cancelled) setLoading(false);\n"
    "        });\n"
    "    });\n"
    "    return () => { cancelled = true; };\n"
    "  }, [load]);\n",
)

export_ui = "apps/web/src/components/export-ui/export-ui.tsx"
replace(
    export_ui,
    "function exactLabel(source: ExportSourceOption): string {\n"
    "  return `${source.artifact_version_id} · ${source.design_document_version_id}`;\n"
    "}\n\n",
    "",
)
replace(
    export_ui,
    "  useEffect(() => {\n"
    "    if (bootstrap.workspace) return;\n"
    "    const controller = new AbortController();\n"
    "    setLoading(true);\n"
    "    gatewayRef.current.loadWorkspace(projectId, controller.signal)\n"
    "      .then((snapshot) => {\n"
    "        setWorkspace(snapshot);\n"
    "        setSourceId(snapshot.active_source_id ?? snapshot.sources[0]?.id ?? \"\");\n"
    "        setHistory(snapshot.history);\n"
    "      })\n"
    "      .catch(() => setError(\"Export workspace could not be loaded.\"))\n"
    "      .finally(() => setLoading(false));\n"
    "    return () => controller.abort();\n"
    "  }, [bootstrap.workspace, projectId]);\n",
    "  useEffect(() => {\n"
    "    if (bootstrap.workspace) return;\n"
    "    const controller = new AbortController();\n"
    "    queueMicrotask(() => {\n"
    "      if (controller.signal.aborted) return;\n"
    "      gatewayRef.current.loadWorkspace(projectId, controller.signal)\n"
    "        .then((snapshot) => {\n"
    "          setWorkspace(snapshot);\n"
    "          setSourceId(snapshot.active_source_id ?? snapshot.sources[0]?.id ?? \"\");\n"
    "          setHistory(snapshot.history);\n"
    "        })\n"
    "        .catch(() => setError(\"Export workspace could not be loaded.\"))\n"
    "        .finally(() => setLoading(false));\n"
    "    });\n"
    "    return () => controller.abort();\n"
    "  }, [bootstrap.workspace, projectId]);\n",
)
replace(
    export_ui,
    "  useEffect(() => {\n"
    "    if (!source) return;\n"
    "    if (sizeMode === \"ORIGINAL\") { setWidth(source.width); setHeight(source.height); }\n"
    "    if (sizeMode === \"2X\") { setWidth(source.width * 2); setHeight(source.height * 2); }\n"
    "  }, [sizeMode, source]);\n\n"
    "  useEffect(() => {\n"
    "    if (!selectedCapability && capabilities[0]) setFormat(capabilities[0].format);\n"
    "  }, [capabilities, selectedCapability]);\n",
    "  const effectiveFormat = selectedCapability?.format ?? format;\n\n"
    "  const selectSource = (nextSourceId: string) => {\n"
    "    setSourceId(nextSourceId);\n"
    "    setJob(null);\n"
    "    setLease(null);\n"
    "    const nextSource = workspace?.sources.find((item) => item.id === nextSourceId) ?? null;\n"
    "    if (!nextSource) return;\n"
    "    if (sizeMode === \"ORIGINAL\") {\n"
    "      setWidth(nextSource.width);\n"
    "      setHeight(nextSource.height);\n"
    "    } else if (sizeMode === \"2X\") {\n"
    "      setWidth(nextSource.width * 2);\n"
    "      setHeight(nextSource.height * 2);\n"
    "    }\n"
    "  };\n\n"
    "  const selectSizeMode = (mode: \"ORIGINAL\" | \"2X\" | \"CUSTOM\" | \"PRESET\") => {\n"
    "    setSizeMode(mode);\n"
    "    if (!source) return;\n"
    "    if (mode === \"ORIGINAL\") {\n"
    "      setWidth(source.width);\n"
    "      setHeight(source.height);\n"
    "    } else if (mode === \"2X\") {\n"
    "      setWidth(source.width * 2);\n"
    "      setHeight(source.height * 2);\n"
    "    }\n"
    "  };\n",
)
replace(
    export_ui,
    "<select value={source.id} onChange={(event) => { setSourceId(event.target.value); setJob(null); setLease(null); }} data-testid=\"source-select\">",
    "<select value={source.id} onChange={(event) => selectSource(event.target.value)} data-testid=\"source-select\">",
)
replace(
    export_ui,
    "className={format === item.format ? styles.formatActive : styles.formatButton}",
    "className={effectiveFormat === item.format ? styles.formatActive : styles.formatButton}",
)
replace(export_ui, "onClick={() => setSizeMode(mode)}", "onClick={() => selectSizeMode(mode)}")

versions = "apps/web/src/components/versions-ui/versions-ui.tsx"
replace(
    versions,
    'import { useEffect, useMemo, useState, type CSSProperties } from "react";\n',
    'import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";\n',
)
replace(
    versions,
    "  const [provenanceError, setProvenanceError] = useState<string | null>(null);\n\n",
    "  const [provenanceError, setProvenanceError] = useState<string | null>(null);\n\n"
    "  const applyWorkspaceSnapshot = useCallback((next: VersionWorkspaceSnapshot, preserveSelection = true) => {\n"
    "    const ids = new Set(next.versions.map((item) => item.version.id));\n"
    "    const fallbackTo = next.versions[0]?.version.id ?? null;\n"
    "    const fallbackFrom = next.versions[1]?.version.id ?? fallbackTo;\n"
    "    setSnapshot(next);\n"
    "    setSelectedBranchId((current) =>\n"
    "      preserveSelection && current && next.branches.some((branch) => branch.id === current)\n"
    "        ? current\n"
    "        : next.active_branch_id,\n"
    "    );\n"
    "    setCompareToId((current) =>\n"
    "      preserveSelection && current && ids.has(current) ? current : fallbackTo,\n"
    "    );\n"
    "    setCompareFromId((current) =>\n"
    "      preserveSelection && current && ids.has(current) ? current : fallbackFrom,\n"
    "    );\n"
    "    setRestoreSourceId((current) =>\n"
    "      preserveSelection && current && ids.has(current) ? current : fallbackFrom,\n"
    "    );\n"
    "    setProvenanceVersionId((current) =>\n"
    "      preserveSelection && current && ids.has(current) ? current : fallbackTo,\n"
    "    );\n"
    "    setCompare(null);\n"
    "    setProvenance(null);\n"
    "    setProvenanceError(null);\n"
    "  }, []);\n\n",
)
replace(
    versions,
    "  useEffect(() => {\n"
    "    let cancelled = false;\n"
    "    setLoading(true);\n"
    "    setError(null);\n"
    "    void queryCache\n"
    "      .fetchQuery(\n"
    "        [\"versions-ui\", projectId],\n"
    "        (signal) => gateway.getWorkspace(activeOrganization.id, projectId, null, signal),\n"
    "        0,\n"
    "      )\n"
    "      .then((next) => {\n"
    "        if (!cancelled) setSnapshot(next);\n"
    "      })\n"
    "      .catch((loadError) => {\n"
    "        if (!cancelled) setError(uiError(loadError));\n"
    "      })\n"
    "      .finally(() => {\n"
    "        if (!cancelled) setLoading(false);\n"
    "      });\n"
    "    return () => {\n"
    "      cancelled = true;\n"
    "    };\n"
    "  }, [activeOrganization.id, gateway, projectId, queryCache]);\n\n"
    "  useEffect(() => {\n"
    "    if (!snapshot) return;\n"
    "    setSelectedBranchId((current) =>\n"
    "      current && snapshot.branches.some((branch) => branch.id === current)\n"
    "        ? current\n"
    "        : snapshot.active_branch_id,\n"
    "    );\n"
    "    const ids = new Set(snapshot.versions.map((item) => item.version.id));\n"
    "    const fallbackTo = snapshot.versions[0]?.version.id ?? null;\n"
    "    const fallbackFrom = snapshot.versions[1]?.version.id ?? fallbackTo;\n"
    "    setCompareToId((current) => (current && ids.has(current) ? current : fallbackTo));\n"
    "    setCompareFromId((current) => (current && ids.has(current) ? current : fallbackFrom));\n"
    "    setRestoreSourceId((current) => (current && ids.has(current) ? current : fallbackFrom));\n"
    "    setProvenanceVersionId((current) => (current && ids.has(current) ? current : fallbackTo));\n"
    "  }, [snapshot]);\n",
    "  useEffect(() => {\n"
    "    let cancelled = false;\n"
    "    queueMicrotask(() => {\n"
    "      if (cancelled) return;\n"
    "      setLoading(true);\n"
    "      setError(null);\n"
    "      void queryCache\n"
    "        .fetchQuery(\n"
    "          [\"versions-ui\", projectId],\n"
    "          (signal) => gateway.getWorkspace(activeOrganization.id, projectId, null, signal),\n"
    "          0,\n"
    "        )\n"
    "        .then((next) => {\n"
    "          if (!cancelled) applyWorkspaceSnapshot(next, false);\n"
    "        })\n"
    "        .catch((loadError) => {\n"
    "          if (!cancelled) setError(uiError(loadError));\n"
    "        })\n"
    "        .finally(() => {\n"
    "          if (!cancelled) setLoading(false);\n"
    "        });\n"
    "    });\n"
    "    return () => {\n"
    "      cancelled = true;\n"
    "    };\n"
    "  }, [activeOrganization.id, applyWorkspaceSnapshot, gateway, projectId, queryCache]);\n",
)
replace(
    versions,
    "    if (!snapshot || !compareFromId || !compareToId) {\n"
    "      setCompare(null);\n"
    "      return;\n"
    "    }\n",
    "    if (!snapshot || !compareFromId || !compareToId) return;\n",
)
replace(
    versions,
    "  useEffect(() => {\n"
    "    if (!snapshot || !provenanceVersionId) {\n"
    "      setProvenance(null);\n"
    "      return;\n"
    "    }\n"
    "    let cancelled = false;\n"
    "    setProvenance(null);\n"
    "    setProvenanceError(null);\n"
    "    if (!snapshot.can_view_provenance) {\n"
    "      setProvenanceError(\"PROVENANCE_FORBIDDEN\");\n"
    "      return;\n"
    "    }\n"
    "    void gateway\n"
    "      .getProvenance(activeOrganization.id, provenanceVersionId)\n"
    "      .then((next) => {\n"
    "        if (!cancelled) setProvenance(next);\n"
    "      })\n"
    "      .catch((provenanceLoadError) => {\n"
    "        if (!cancelled) setProvenanceError(uiError(provenanceLoadError));\n"
    "      });\n"
    "    return () => {\n"
    "      cancelled = true;\n"
    "    };\n"
    "  }, [activeOrganization.id, gateway, provenanceVersionId, snapshot]);\n",
    "  useEffect(() => {\n"
    "    if (!snapshot || !provenanceVersionId) return;\n"
    "    let cancelled = false;\n"
    "    if (!snapshot.can_view_provenance) {\n"
    "      queueMicrotask(() => {\n"
    "        if (!cancelled) setProvenanceError(\"PROVENANCE_FORBIDDEN\");\n"
    "      });\n"
    "      return () => {\n"
    "        cancelled = true;\n"
    "      };\n"
    "    }\n"
    "    void gateway\n"
    "      .getProvenance(activeOrganization.id, provenanceVersionId)\n"
    "      .then((next) => {\n"
    "        if (!cancelled) setProvenance(next);\n"
    "      })\n"
    "      .catch((provenanceLoadError) => {\n"
    "        if (!cancelled) setProvenanceError(uiError(provenanceLoadError));\n"
    "      });\n"
    "    return () => {\n"
    "      cancelled = true;\n"
    "    };\n"
    "  }, [activeOrganization.id, gateway, provenanceVersionId, snapshot]);\n",
)
replace(
    versions,
    "  const switchArtifact = async (artifactId: string) => {\n",
    "  const chooseCompareFrom = (versionId: string) => {\n"
    "    setCompareFromId(versionId);\n"
    "    setCompare(null);\n"
    "  };\n\n"
    "  const chooseCompareTo = (versionId: string) => {\n"
    "    setCompareToId(versionId);\n"
    "    setCompare(null);\n"
    "  };\n\n"
    "  const chooseProvenance = (versionId: string) => {\n"
    "    setProvenanceVersionId(versionId);\n"
    "    setProvenance(null);\n"
    "    setProvenanceError(null);\n"
    "  };\n\n"
    "  const switchArtifact = async (artifactId: string) => {\n",
)
replace(
    versions,
    "      setSnapshot(next);\n"
    "      setSelectedBranchId(next.active_branch_id);\n"
    "      setCompareFromId(null);\n"
    "      setCompareToId(null);\n"
    "      setRestoreSourceId(null);\n"
    "      setProvenanceVersionId(null);\n"
    "      setCompareMode(\"SIDE_BY_SIDE\");\n",
    "      applyWorkspaceSnapshot(next, false);\n"
    "      setCompareMode(\"SIDE_BY_SIDE\");\n",
)
replace(
    versions,
    "    const beforeFrom = compareFromId;\n"
    "    const beforeTo = compareToId;\n"
    "    setBusy(true);\n",
    "    setBusy(true);\n",
)
replace(
    versions,
    "      setSnapshot(next);\n"
    "      const ids = new Set(next.versions.map((item) => item.version.id));\n"
    "      if (beforeFrom && ids.has(beforeFrom)) setCompareFromId(beforeFrom);\n"
    "      if (beforeTo && ids.has(beforeTo)) setCompareToId(beforeTo);\n",
    "      applyWorkspaceSnapshot(next, true);\n",
)
replace(
    versions,
    "      setSnapshot(next);\n"
    "      setSelectedBranchId(next.active_branch_id);\n"
    "      setCompareToId(next.head_version_id);\n"
    "      setProvenanceVersionId(next.head_version_id);\n",
    "      applyWorkspaceSnapshot(next, true);\n"
    "      setSelectedBranchId(next.active_branch_id);\n"
    "      chooseCompareTo(next.head_version_id);\n"
    "      chooseProvenance(next.head_version_id);\n",
)
replace(
    versions,
    "      setSnapshot(next);\n"
    "      setSelectedBranchId(next.active_branch_id);\n"
    "      setForkName(\"\");\n",
    "      applyWorkspaceSnapshot(next, true);\n"
    "      setSelectedBranchId(next.active_branch_id);\n"
    "      setForkName(\"\");\n",
)
replace(versions, "onClick={() => setCompareFromId(item.version.id)}", "onClick={() => chooseCompareFrom(item.version.id)}")
replace(versions, "onClick={() => setCompareToId(item.version.id)}", "onClick={() => chooseCompareTo(item.version.id)}")
replace(versions, "onClick={() => setProvenanceVersionId(item.version.id)}", "onClick={() => chooseProvenance(item.version.id)}")
replace(versions, "onChange={(event) => setCompareFromId(event.target.value)}", "onChange={(event) => chooseCompareFrom(event.target.value)}")
replace(versions, "onChange={(event) => setCompareToId(event.target.value)}", "onChange={(event) => chooseCompareTo(event.target.value)}")

admin = "apps/web/src/lib/admin-console/admin-gateway.ts"
for signature in [
    "  async retryRun(runId: string, _input: SensitiveActionInput): Promise<AdminRun> {\n",
    "  async cancelRun(runId: string, _input: SensitiveActionInput): Promise<AdminRun> {\n",
    "  async disableProvider(providerId: string, expiresAt: string, _input: SensitiveActionInput): Promise<AdminProvider> {\n",
    "  async requeue(queueItemId: string, _input: SensitiveActionInput): Promise<AdminQueueItem> {\n",
    "  async setRegistryEnabled(item: AdminRegistryItem, enabled: boolean, _input: SensitiveActionInput): Promise<AdminRegistryItem> {\n",
    "  async adjustBilling(organizationId: string, deltaCredits: number, _input: SensitiveActionInput): Promise<AdminBillingView> {\n",
]:
    replace(admin, signature, signature + "    void _input;\n")
replace(
    admin,
    "  async revealPii(userId: string, _reason: string, _ticketRef: string): Promise<RevealedPii> {\n",
    "  async revealPii(userId: string, _reason: string, _ticketRef: string): Promise<RevealedPii> {\n"
    "    void _reason;\n"
    "    void _ticketRef;\n",
)
replace(
    admin,
    "  async startViewAs(userId: string, organizationId: string, _reason: string, _ticketRef: string): Promise<ViewAsSession> {\n",
    "  async startViewAs(userId: string, organizationId: string, _reason: string, _ticketRef: string): Promise<ViewAsSession> {\n"
    "    void _reason;\n"
    "    void _ticketRef;\n",
)

approval = "apps/web/src/lib/approval-ui/contracts.test.ts"
replace(approval, 'import { describe, expect, it } from "vitest";\n', 'import { expect, it } from "vitest";\n')
