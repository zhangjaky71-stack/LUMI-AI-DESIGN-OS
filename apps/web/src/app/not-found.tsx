import Link from "next/link";

export default function NotFound() {
  return (
    <main className="simple-state-page">
      <p className="eyebrow">404</p>
      <h1>页面不存在</h1>
      <p>返回 LUMI 工作台继续。</p>
      <Link className="secondary-button" href="/app">
        返回工作台
      </Link>
    </main>
  );
}
