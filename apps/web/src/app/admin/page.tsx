import Link from "next/link";

export default function AdminEntryPage() {
  return (
    <main className="simple-state-page">
      <p className="eyebrow">ADMIN</p>
      <h1>管理控制台尚未开放</h1>
      <p>该入口将由独立的服务端权限策略保护。当前不会仅依赖客户端角色显示来授权。</p>
      <Link className="secondary-button" href="/app">返回工作台</Link>
    </main>
  );
}
