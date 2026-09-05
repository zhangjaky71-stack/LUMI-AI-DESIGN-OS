export function ShellSection({
  eyebrow,
  title,
  description,
  children,
}: Readonly<{
  eyebrow: string;
  title: string;
  description: string;
  children?: React.ReactNode;
}>) {
  return (
    <section className="shell-section">
      <div className="section-heading">
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="section-description">{description}</p>
      </div>
      {children ?? (
        <div className="empty-state" role="status">
          <div className="empty-state-orb" aria-hidden="true" />
          <h2>工作区已就绪</h2>
          <p>数据服务接通后，此区域会自动加载当前组织的内容。</p>
        </div>
      )}
    </section>
  );
}
