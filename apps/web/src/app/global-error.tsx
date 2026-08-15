"use client";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="zh-CN">
      <body>
        <main className="simple-state-page">
          <p className="eyebrow">SYSTEM ERROR</p>
          <h1>LUMI 暂时无法加载</h1>
          <p>没有向页面暴露内部堆栈。你可以安全重试。</p>
          <button className="primary-button" type="button" onClick={reset}>重试</button>
        </main>
      </body>
    </html>
  );
}
