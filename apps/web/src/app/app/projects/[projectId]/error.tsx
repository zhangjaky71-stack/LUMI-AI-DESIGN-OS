"use client";

export default function ProjectWorkspaceError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <section className="route-error" role="alert">
      <p className="eyebrow">PROJECT ERROR</p>
      <h1>项目工作区发生错误</h1>
      <p>
        你的项目数据没有被覆盖。请求标识：
        <code>{error.digest ?? "unavailable"}</code>
      </p>
      <button className="secondary-button" type="button" onClick={reset}>
        重新加载
      </button>
    </section>
  );
}
