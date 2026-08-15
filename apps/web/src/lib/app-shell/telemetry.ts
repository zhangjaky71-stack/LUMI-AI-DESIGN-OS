export type TelemetryEventName =
  | "page.viewed"
  | "project.opened"
  | "command.initiated"
  | "organization.switched";

export type TelemetryScalar = string | number | boolean | null;
export type TelemetryProperties = Readonly<Record<string, TelemetryScalar>>;

export interface TelemetryAdapter {
  emit(event: TelemetryEventName, properties: TelemetryProperties): void | Promise<void>;
}

const SENSITIVE_KEY = /(prompt|image|asset.?url|token|secret|password|authorization|cookie|email|content)/i;

export function sanitizeTelemetryProperties(properties: TelemetryProperties): TelemetryProperties {
  for (const key of Object.keys(properties)) {
    if (SENSITIVE_KEY.test(key)) throw new Error(`TELEMETRY_SENSITIVE_PROPERTY_FORBIDDEN:${key}`);
  }
  return Object.freeze({ ...properties });
}

export class NoopTelemetryAdapter implements TelemetryAdapter {
  emit(): void {}
}

export class SafeTelemetry {
  readonly #adapter: TelemetryAdapter;

  constructor(adapter: TelemetryAdapter = new NoopTelemetryAdapter()) {
    this.#adapter = adapter;
  }

  emit(event: TelemetryEventName, properties: TelemetryProperties = {}): void {
    void this.#adapter.emit(event, sanitizeTelemetryProperties(properties));
  }
}
