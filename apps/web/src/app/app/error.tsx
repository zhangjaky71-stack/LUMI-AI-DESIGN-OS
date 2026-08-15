"use client";

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const requestId = error.digest ?? "unavailable";

  return (
    <section className="route-error" role="alert">
      <p className="eyebrow">WORKSPACE ERROR</p>
      <h1>工作区暂时无法加载</h1>
      <p>
        请重试。若问题持续，请向支持团队提供请求标识：
        <code>{requestId}</code>
      </p>
      <button className="secondary-button" type="button" onClick={reset}>
        重试
      </button>
    </section>
  );
}
