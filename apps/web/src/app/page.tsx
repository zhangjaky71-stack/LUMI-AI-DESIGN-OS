import Link from "next/link";

export default function Home() {
  return (
    <main className="landing-page">
      <nav className="landing-nav" aria-label="首页导航">
        <Link className="brand-lockup" href="/" aria-label="LUMI 首页">
          <span className="brand-mark" aria-hidden="true">L</span>
          <span>LUMI</span>
        </Link>
        <Link className="text-link" href="/login">登录</Link>
      </nav>
      <section className="hero-panel">
        <p className="eyebrow">AI DESIGN OPERATING SYSTEM</p>
        <h1>把创意、生成、画布与质量闭环放进同一个工作空间。</h1>
        <p className="hero-copy">LUMI 将多智能体、Design IR、Canvas、Artifact、生成与自动修复组织成可审计的产品级设计工作流。</p>
        <div className="hero-actions">
          <Link className="primary-button" href="/login">进入工作台</Link>
          <Link className="secondary-button" href="/signup">创建账户</Link>
        </div>
        <div className="hero-grid" aria-label="平台能力">
          <div><span>01</span><strong>Agent-native</strong><p>规划、执行、批评与修复统一编排。</p></div>
          <div><span>02</span><strong>Canvas-native</strong><p>结构化 Design IR 驱动可编辑画布。</p></div>
          <div><span>03</span><strong>Artifact-native</strong><p>版本、血缘、质量与审批全程可追溯。</p></div>
        </div>
      </section>
    </main>
  );
}
