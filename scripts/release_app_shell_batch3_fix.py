from __future__ import annotations

from pathlib import Path


def replace(path: str, old: str, new: str, *, count: int = 1) -> None:
    target = Path(path)
    source = target.read_text(encoding="utf-8")
    found = source.count(old)
    if found != count:
        raise SystemExit(
            f"expected Batch 3 target count mismatch: {path}: wanted {count}, found {found}: {old!r}"
        )
    target.write_text(source.replace(old, new, count), encoding="utf-8")


canvas = "apps/web/src/components/infinite-canvas/infinite-canvas.tsx"
replace(
    canvas,
    "/* eslint-disable react-hooks/exhaustive-deps -- CanvasController is an imperative runtime; global shortcut and observer bridges intentionally read current refs. */\n\n",
    "",
)
replace(
    canvas,
    '  const [online, setOnline] = useState(true);\n',
    '  const [online, setOnline] = useState(() =>\n'
    '    typeof navigator === "undefined" ? true : navigator.onLine,\n'
    '  );\n',
)
replace(
    canvas,
    '  const [loading, setLoading] = useState(true);\n\n'
    '  const syncRuntime = useCallback(() => {\n'
    '    if (controllerRef.current) setRuntime(controllerRef.current.snapshot());\n'
    '  }, []);\n',
    '  const [loading, setLoading] = useState(true);\n'
    '  const [serverVersion, setServerVersion] = useState(0);\n'
    '  const [historyCount, setHistoryCount] = useState(0);\n'
    '  const [redoCount, setRedoCount] = useState(0);\n'
    '  const [clipboardCount, setClipboardCount] = useState(0);\n'
    '  const [draggingNodeIds, setDraggingNodeIds] = useState<readonly string[]>([]);\n\n'
    '  const syncRuntime = useCallback(() => {\n'
    '    if (controllerRef.current) setRuntime(controllerRef.current.snapshot());\n'
    '  }, []);\n\n'
    '  const syncHistoryCounts = useCallback(() => {\n'
    '    setHistoryCount(historyRef.current.length);\n'
    '    setRedoCount(redoRef.current.length);\n'
    '  }, []);\n',
)
replace(
    canvas,
    '      serverVersionRef.current = nextServerVersion;\n'
    '      autosaveRef.current.acknowledge(batch.count, nextServerVersion);\n',
    '      serverVersionRef.current = nextServerVersion;\n'
    '      setServerVersion(nextServerVersion);\n'
    '      autosaveRef.current.acknowledge(batch.count, nextServerVersion);\n',
)
replace(
    canvas,
    '  scheduleFlushRef.current = scheduleFlush;\n',
    '  useEffect(() => {\n'
    '    scheduleFlushRef.current = scheduleFlush;\n'
    '  }, [scheduleFlush]);\n',
)
replace(
    canvas,
    '  const recordHistory = useCallback((before: DesignDocument, forward: readonly DesignOperation[]) => {\n'
    '    if (!forward.length) return;\n'
    '    historyRef.current.push({ forward: structuredClone(forward), inverse: invertOperations(before, forward) });\n'
    '    if (historyRef.current.length > 100) historyRef.current.shift();\n'
    '    redoRef.current = [];\n'
    '  }, []);\n',
    '  const recordHistory = useCallback(\n'
    '    (before: DesignDocument, forward: readonly DesignOperation[]) => {\n'
    '      if (!forward.length) return;\n'
    '      historyRef.current.push({\n'
    '        forward: structuredClone(forward),\n'
    '        inverse: invertOperations(before, forward),\n'
    '      });\n'
    '      if (historyRef.current.length > 100) historyRef.current.shift();\n'
    '      redoRef.current = [];\n'
    '      syncHistoryCounts();\n'
    '    },\n'
    '    [syncHistoryCounts],\n'
    '  );\n',
)
replace(
    canvas,
    '  useEffect(() => {\n'
    '    let cancelled = false;\n'
    '    setLoading(true);\n'
    '    void gateway\n'
    '      .getDocument(activeOrganization.id, projectId)\n'
    '      .then((snapshot) => {\n'
    '        if (cancelled) return;\n'
    '        serverVersionRef.current = getDocumentVersion(snapshot.document);\n'
    '        const controller = new CanvasController(snapshot.document, {\n'
    '          initial_viewport: { width: 1100, height: 760 },\n'
    '        });\n'
    '        controllerRef.current?.destroy();\n'
    '        controllerRef.current = controller;\n'
    '        controller.fitAll(72);\n'
    '        autosaveRef.current.clear();\n'
    '        setPendingCount(0);\n'
    '        setSyncState("SAVED");\n'
    '        setRuntime(controller.snapshot());\n'
    '        emitContext("SAVED");\n'
    '      })\n'
    '      .catch((error) => setNotice(`Canvas load failed: ${errorMessage(error)}`))\n'
    '      .finally(() => {\n'
    '        if (!cancelled) setLoading(false);\n'
    '      });\n'
    '    return () => {\n'
    '      cancelled = true;\n'
    '      editorRef.current = null;\n'
    '      controllerRef.current?.destroy();\n'
    '      controllerRef.current = null;\n'
    '      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);\n'
    '    };\n'
    '  }, [activeOrganization.id, editorRef, emitContext, gateway, projectId]);\n',
    '  useEffect(() => {\n'
    '    let cancelled = false;\n'
    '    queueMicrotask(() => {\n'
    '      if (cancelled) return;\n'
    '      setLoading(true);\n'
    '      void gateway\n'
    '        .getDocument(activeOrganization.id, projectId)\n'
    '        .then((snapshot) => {\n'
    '          if (cancelled) return;\n'
    '          const nextServerVersion = getDocumentVersion(snapshot.document);\n'
    '          serverVersionRef.current = nextServerVersion;\n'
    '          setServerVersion(nextServerVersion);\n'
    '          const controller = new CanvasController(snapshot.document, {\n'
    '            initial_viewport: { width: 1100, height: 760 },\n'
    '          });\n'
    '          controllerRef.current?.destroy();\n'
    '          controllerRef.current = controller;\n'
    '          controller.fitAll(72);\n'
    '          autosaveRef.current.clear();\n'
    '          historyRef.current = [];\n'
    '          redoRef.current = [];\n'
    '          setHistoryCount(0);\n'
    '          setRedoCount(0);\n'
    '          setPendingCount(0);\n'
    '          setSyncState("SAVED");\n'
    '          setRuntime(controller.snapshot());\n'
    '          emitContext("SAVED");\n'
    '        })\n'
    '        .catch((error) => {\n'
    '          if (!cancelled) setNotice(`Canvas load failed: ${errorMessage(error)}`);\n'
    '        })\n'
    '        .finally(() => {\n'
    '          if (!cancelled) setLoading(false);\n'
    '        });\n'
    '    });\n'
    '    return () => {\n'
    '      cancelled = true;\n'
    '      editorRef.current = null;\n'
    '      controllerRef.current?.destroy();\n'
    '      controllerRef.current = null;\n'
    '      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);\n'
    '    };\n'
    '  }, [activeOrganization.id, editorRef, emitContext, gateway, projectId]);\n',
)
replace(canvas, '    setOnline(navigator.onLine);\n', '')
replace(
    canvas,
    '    const transform = controller.beginTransform(`product-drag-${Date.now()}`);\n',
    '    const transform = controller.beginTransform(\n'
    '      `product-drag-${event.pointerId}-${Math.round(event.timeStamp)}`,\n'
    '    );\n',
)
replace(
    canvas,
    '    dragRef.current = {\n'
    '      pointerId: event.pointerId,\n'
    '      startX: event.clientX,\n'
    '      startY: event.clientY,\n'
    '      transform,\n'
    '      before: controller.snapshot().document,\n'
    '      nodeIds: transform.ids,\n'
    '    };\n'
    '    event.currentTarget.setPointerCapture(event.pointerId);\n',
    '    dragRef.current = {\n'
    '      pointerId: event.pointerId,\n'
    '      startX: event.clientX,\n'
    '      startY: event.clientY,\n'
    '      transform,\n'
    '      before: controller.snapshot().document,\n'
    '      nodeIds: transform.ids,\n'
    '    };\n'
    '    setDraggingNodeIds(transform.ids);\n'
    '    event.currentTarget.setPointerCapture(event.pointerId);\n',
)
replace(
    canvas,
    '    dragRef.current = null;\n'
    '    setDragDelta({ x: 0, y: 0 });\n',
    '    dragRef.current = null;\n'
    '    setDraggingNodeIds([]);\n'
    '    setDragDelta({ x: 0, y: 0 });\n',
)
replace(
    canvas,
    '      operation_id: `lock-${nodeId}-${Date.now()}`,\n',
    '      operation_id: `lock-${nodeId}-${crypto.randomUUID()}`,\n',
)
replace(
    canvas,
    '      operation_id: `arrange-${nodeId}-${Date.now()}`,\n',
    '      operation_id: `arrange-${nodeId}-${crypto.randomUUID()}`,\n',
)
replace(
    canvas,
    '    const operations: DesignOperation[] = ids.map((id, index) => ({\n'
    '      operation_id: `delete-${Date.now()}-${index}`,\n',
    '    const deleteBatchId = crypto.randomUUID();\n'
    '    const operations: DesignOperation[] = ids.map((id, index) => ({\n'
    '      operation_id: `delete-${deleteBatchId}-${index}`,\n',
)
replace(
    canvas,
    '  editorRef.current = editorApi;\n',
    '  useEffect(() => {\n'
    '    editorRef.current = editorApi;\n'
    '  });\n',
)
replace(
    canvas,
    '  const undo = () => {\n'
    '    const controller = controllerRef.current;\n'
    '    const entry = historyRef.current.pop();\n'
    '    if (!controller || !entry) return;\n'
    '    const document = controller.snapshot().document;\n'
    '    const operations = rebaseOperationsVersion(entry.inverse, getDocumentVersion(document), "undo");\n'
    '    const result = executeOperations(document, operations);\n'
    '    if (!result.ok) {\n'
    '      historyRef.current.push(entry);\n'
    '      setNotice("Undo 被当前文档约束拒绝。");\n'
    '      return;\n'
    '    }\n'
    '    redoRef.current.push(entry);\n'
    '    controller.replaceDocument(result.document, false);\n'
    '    enqueue(operations);\n'
    '    syncRuntime();\n'
    '  };\n',
    '  const undo = () => {\n'
    '    const controller = controllerRef.current;\n'
    '    if (!controller) return;\n'
    '    const entry = historyRef.current.pop();\n'
    '    if (!entry) return;\n'
    '    const document = controller.snapshot().document;\n'
    '    const operations = rebaseOperationsVersion(entry.inverse, getDocumentVersion(document), "undo");\n'
    '    const result = executeOperations(document, operations);\n'
    '    if (!result.ok) {\n'
    '      historyRef.current.push(entry);\n'
    '      syncHistoryCounts();\n'
    '      setNotice("Undo 被当前文档约束拒绝。");\n'
    '      return;\n'
    '    }\n'
    '    redoRef.current.push(entry);\n'
    '    syncHistoryCounts();\n'
    '    controller.replaceDocument(result.document, false);\n'
    '    enqueue(operations);\n'
    '    syncRuntime();\n'
    '  };\n',
)
replace(
    canvas,
    '  const redo = () => {\n'
    '    const controller = controllerRef.current;\n'
    '    const entry = redoRef.current.pop();\n'
    '    if (!controller || !entry) return;\n'
    '    const document = controller.snapshot().document;\n'
    '    const operations = rebaseOperationsVersion(entry.forward, getDocumentVersion(document), "redo");\n'
    '    const result = executeOperations(document, operations);\n'
    '    if (!result.ok) {\n'
    '      redoRef.current.push(entry);\n'
    '      setNotice("Redo 被当前文档约束拒绝。");\n'
    '      return;\n'
    '    }\n'
    '    historyRef.current.push(entry);\n'
    '    controller.replaceDocument(result.document, false);\n'
    '    enqueue(operations);\n'
    '    syncRuntime();\n'
    '  };\n',
    '  const redo = () => {\n'
    '    const controller = controllerRef.current;\n'
    '    if (!controller) return;\n'
    '    const entry = redoRef.current.pop();\n'
    '    if (!entry) return;\n'
    '    const document = controller.snapshot().document;\n'
    '    const operations = rebaseOperationsVersion(entry.forward, getDocumentVersion(document), "redo");\n'
    '    const result = executeOperations(document, operations);\n'
    '    if (!result.ok) {\n'
    '      redoRef.current.push(entry);\n'
    '      syncHistoryCounts();\n'
    '      setNotice("Redo 被当前文档约束拒绝。");\n'
    '      return;\n'
    '    }\n'
    '    historyRef.current.push(entry);\n'
    '    syncHistoryCounts();\n'
    '    controller.replaceDocument(result.document, false);\n'
    '    enqueue(operations);\n'
    '    syncRuntime();\n'
    '  };\n',
)
replace(
    canvas,
    '  const copy = () => {\n'
    '    clipboardRef.current = controllerRef.current?.selection.snapshot().ids ?? [];\n'
    '    setNotice(clipboardRef.current.length ? `已复制 ${clipboardRef.current.length} 个对象。` : "没有可复制的对象。");\n'
    '  };\n',
    '  const copy = () => {\n'
    '    clipboardRef.current = controllerRef.current?.selection.snapshot().ids ?? [];\n'
    '    const nextClipboardCount = clipboardRef.current.length;\n'
    '    setClipboardCount(nextClipboardCount);\n'
    '    setNotice(nextClipboardCount ? `已复制 ${nextClipboardCount} 个对象。` : "没有可复制的对象。");\n'
    '  };\n',
)
replace(
    canvas,
    '        event.shiftKey ? redo() : undo();\n',
    '        if (event.shiftKey) redo();\n'
    '        else undo();\n',
)
replace(
    canvas,
    '        const session = controller.beginTransform(`nudge-${Date.now()}`);\n',
    '        const session = controller.beginTransform(\n'
    '          `nudge-${event.code}-${Math.round(event.timeStamp)}`,\n'
    '        );\n',
)
replace(
    canvas,
    '      serverVersionRef.current = version;\n'
    '      controllerRef.current?.replaceDocument(replay.document, false);\n',
    '      serverVersionRef.current = version;\n'
    '      setServerVersion(version);\n'
    '      controllerRef.current?.replaceDocument(replay.document, false);\n',
)
replace(
    canvas,
    '      serverVersionRef.current = getDocumentVersion(canonical.document);\n'
    '      autosaveRef.current.clear();\n'
    '      historyRef.current = [];\n'
    '      redoRef.current = [];\n',
    '      const nextServerVersion = getDocumentVersion(canonical.document);\n'
    '      serverVersionRef.current = nextServerVersion;\n'
    '      setServerVersion(nextServerVersion);\n'
    '      autosaveRef.current.clear();\n'
    '      historyRef.current = [];\n'
    '      redoRef.current = [];\n'
    '      syncHistoryCounts();\n',
)
replace(
    canvas,
    '  const draggingIds = new Set(dragRef.current?.nodeIds ?? []);\n',
    '  const draggingIds = new Set(draggingNodeIds);\n',
)
replace(canvas, 'disabled={!historyRef.current.length}', 'disabled={historyCount === 0}')
replace(canvas, 'disabled={!redoRef.current.length}', 'disabled={redoCount === 0}')
replace(canvas, 'disabled={!clipboardRef.current.length}', 'disabled={clipboardCount === 0}')
replace(canvas, '<span>Server v{serverVersionRef.current}</span>', '<span>Server v{serverVersion}</span>')

canvas_source = Path(canvas).read_text(encoding="utf-8")
if "Date.now()" in canvas_source:
    raise SystemExit("Batch 3 left Date.now() in Infinite Canvas component")


gateway = "apps/web/src/lib/infinite-canvas/canvas-gateway.ts"
replace(
    gateway,
    'function externalEditOperation(documentId: string, version: number): DesignOperation {\n',
    'function externalEditOperation(\n'
    '  documentId: string,\n'
    '  targetId: string,\n'
    '  version: number,\n'
    '): DesignOperation {\n',
)
replace(gateway, '    target_ids: ["frame-square"],\n', '    target_ids: [targetId],\n')
replace(
    gateway,
    '    if (this.#conflictOnNextSave) {\n'
    '      const external = executeOperations(this.#snapshot.document, [\n'
    '        externalEditOperation(this.#snapshot.document.document_id, currentVersion),\n'
    '      ]);\n',
    '    if (this.#conflictOnNextSave) {\n'
    '      const externalTargetId =\n'
    '        Object.values(this.#snapshot.document.nodes).find((node) => node.kind === "FRAME")?.id ??\n'
    '        this.#snapshot.document.root_id;\n'
    '      const external = executeOperations(this.#snapshot.document, [\n'
    '        externalEditOperation(\n'
    '          this.#snapshot.document.document_id,\n'
    '          externalTargetId,\n'
    '          currentVersion,\n'
    '        ),\n'
    '      ]);\n',
)

fallback = "apps/web/e2e/canvas-renderer-fallback.spec.ts"
replace(fallback, '      type FabricObject = object;\n', '      type FabricObject = Record<string, unknown>;\n')
