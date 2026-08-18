"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { OperationDescriptor } from "@lumi/canvas-sdk";

import { ApiError } from "@/lib/api/problem";
import { saveCanvasCommands } from "@/lib/canvas/api";
import type { CanvasProjection, CanvasSaveState } from "@/lib/canvas/types";
import { newUuid7 } from "@/lib/canvas/uuid7";

const MAX_PENDING_COMMANDS = 120;
const AUTOSAVE_DELAY_MS = 700;

type ActiveBatch = {
  id: string;
  count: number;
  descriptors: readonly OperationDescriptor[];
  base: CanvasProjection;
};

export function useCanvasAutosave({
  organizationId,
  initialProjection,
  onCanonicalProjection,
}: {
  organizationId: string;
  initialProjection: CanvasProjection;
  onCanonicalProjection: (projection: CanvasProjection, queueDrained: boolean) => void;
}) {
  const projectionRef = useRef(initialProjection);
  const pendingRef = useRef<OperationDescriptor[]>([]);
  const activeBatchRef = useRef<ActiveBatch | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const flushingRef = useRef(false);
  const mountedRef = useRef(true);
  const [saveState, setSaveState] = useState<CanvasSaveState>("saved");
  const [pendingCount, setPendingCount] = useState(0);
  const [message, setMessage] = useState<string | null>(null);

  const setQueueCount = useCallback(() => {
    if (mountedRef.current) setPendingCount(pendingRef.current.length);
  }, []);

  const flush = useCallback(async () => {
    if (flushingRef.current || saveState === "conflict") return;
    if (!pendingRef.current.length) {
      setSaveState("saved");
      return;
    }
    let batch = activeBatchRef.current;
    if (!batch) {
      const count = Math.min(pendingRef.current.length, MAX_PENDING_COMMANDS);
      batch = {
        id: newUuid7(),
        count,
        descriptors: pendingRef.current.slice(0, count),
        base: projectionRef.current,
      };
      activeBatchRef.current = batch;
    }
    flushingRef.current = true;
    setSaveState("saving");
    setMessage(null);
    try {
      const next = await saveCanvasCommands(
        organizationId,
        batch.base,
        batch.descriptors,
        batch.id,
      );
      if (!mountedRef.current) return;
      pendingRef.current.splice(0, batch.count);
      projectionRef.current = next;
      activeBatchRef.current = null;
      setQueueCount();
      const drained = pendingRef.current.length === 0;
      onCanonicalProjection(next, drained);
      setSaveState(drained ? "saved" : "dirty");
      if (!drained) queueMicrotask(() => void flush());
    } catch (error) {
      if (!mountedRef.current) return;
      if (error instanceof ApiError && error.status === 409) {
        setSaveState("conflict");
        setMessage("This document changed elsewhere. Local edits are preserved but saving is paused until you reload the canonical version.");
      } else if (!navigator.onLine || error instanceof TypeError) {
        setSaveState("offline");
        setMessage("Offline — unsaved canvas commands are kept locally and will retry after reconnecting.");
      } else {
        setSaveState("error");
        setMessage(error instanceof Error ? error.message : "Canvas autosave failed.");
      }
    } finally {
      flushingRef.current = false;
    }
  }, [onCanonicalProjection, organizationId, saveState, setQueueCount]);

  const scheduleFlush = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => void flush(), AUTOSAVE_DELAY_MS);
  }, [flush]);

  const enqueue = useCallback((descriptors: readonly OperationDescriptor[]): boolean => {
    if (!descriptors.length) return true;
    if (saveState === "conflict") return false;
    if (pendingRef.current.length + descriptors.length > MAX_PENDING_COMMANDS) {
      setSaveState("error");
      setMessage(`Autosave queue limit (${MAX_PENDING_COMMANDS}) reached. Reconnect or reload before editing more.`);
      return false;
    }
    pendingRef.current.push(...descriptors.map(cloneDescriptor));
    setQueueCount();
    setSaveState(navigator.onLine ? "dirty" : "offline");
    scheduleFlush();
    return true;
  }, [saveState, scheduleFlush, setQueueCount]);

  const adoptProjection = useCallback((projection: CanvasProjection) => {
    projectionRef.current = projection;
    pendingRef.current = [];
    activeBatchRef.current = null;
    if (timerRef.current) clearTimeout(timerRef.current);
    setQueueCount();
    setSaveState("saved");
    setMessage(null);
  }, [setQueueCount]);

  const retry = useCallback(() => {
    if (saveState === "conflict") return;
    setSaveState(pendingRef.current.length ? "dirty" : "saved");
    void flush();
  }, [flush, saveState]);

  useEffect(() => {
    mountedRef.current = true;
    const online = () => {
      if (pendingRef.current.length) {
        setSaveState("dirty");
        void flush();
      }
    };
    const offline = () => {
      if (pendingRef.current.length) setSaveState("offline");
    };
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (!pendingRef.current.length) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("online", online);
    window.addEventListener("offline", offline);
    window.addEventListener("beforeunload", beforeUnload);
    return () => {
      mountedRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
      window.removeEventListener("online", online);
      window.removeEventListener("offline", offline);
      window.removeEventListener("beforeunload", beforeUnload);
    };
  }, [flush]);

  return {
    saveState,
    pendingCount,
    message,
    enqueue,
    flushNow: flush,
    retry,
    adoptProjection,
    canEdit: saveState !== "conflict" && pendingCount < MAX_PENDING_COMMANDS,
  };
}

function cloneDescriptor(descriptor: OperationDescriptor): OperationDescriptor {
  return {
    type: descriptor.type,
    targetIds: [...descriptor.targetIds],
    payload: structuredClone(descriptor.payload),
    ...(descriptor.reason ? { reason: descriptor.reason } : {}),
  };
}
