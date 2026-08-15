"use client";

import { useEffect } from "react";

import {
  emitBrowserTelemetry,
  normalizeTelemetryRoute,
  reportCanvasError,
  reportWebVital,
} from "../lib/observability/browser";

export function BrowserObservability() {
  useEffect(() => {
    const route = () => normalizeTelemetryRoute(window.location.pathname);

    const onError = () => {
      emitBrowserTelemetry({
        version: 1,
        kind: "runtime_error",
        name: "window_error",
        route: route(),
        errorCode: "window_error",
      });
    };
    const onUnhandledRejection = () => {
      emitBrowserTelemetry({
        version: 1,
        kind: "runtime_error",
        name: "unhandled_rejection",
        route: route(),
        errorCode: "unhandled_rejection",
      });
    };
    const onCanvasError = (event: Event) => {
      const detail = (event as CustomEvent<{ code?: string }>).detail;
      reportCanvasError(detail?.code, route());
    };

    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onUnhandledRejection);
    window.addEventListener("lumi:canvas-error", onCanvasError);

    const observers: PerformanceObserver[] = [];
    const supported = new Set(PerformanceObserver.supportedEntryTypes ?? []);

    const navigation = performance.getEntriesByType("navigation")[0] as
      | PerformanceNavigationTiming
      | undefined;
    if (navigation && navigation.responseStart >= 0) {
      reportWebVital("ttfb_ms", navigation.responseStart, route());
    }

    if (supported.has("largest-contentful-paint")) {
      const observer = new PerformanceObserver((list) => {
        const entries = list.getEntries();
        const latest = entries.at(-1);
        if (latest) reportWebVital("lcp_ms", latest.startTime, route());
      });
      observer.observe({ type: "largest-contentful-paint", buffered: true });
      observers.push(observer);
    }

    if (supported.has("layout-shift")) {
      let cls = 0;
      const observer = new PerformanceObserver((list) => {
        for (const raw of list.getEntries()) {
          const entry = raw as PerformanceEntry & {
            value?: number;
            hadRecentInput?: boolean;
          };
          if (!entry.hadRecentInput && typeof entry.value === "number") cls += entry.value;
        }
        reportWebVital("cls", cls, route());
      });
      observer.observe({ type: "layout-shift", buffered: true });
      observers.push(observer);
    }

    if (supported.has("event")) {
      let longest = 0;
      const observer = new PerformanceObserver((list) => {
        for (const raw of list.getEntries()) {
          const duration = raw.duration;
          if (Number.isFinite(duration)) longest = Math.max(longest, duration);
        }
        if (longest > 0) reportWebVital("inp_ms", longest, route());
      });
      observer.observe({ type: "event", buffered: true, durationThreshold: 40 });
      observers.push(observer);
    }

    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onUnhandledRejection);
      window.removeEventListener("lumi:canvas-error", onCanvasError);
      for (const observer of observers) observer.disconnect();
    };
  }, []);

  return null;
}
