import Link from "next/link";
import { ShellSection } from "@/components/app-shell/shell-section";

export default function SettingsPage() {
  return (
    <ShellSection
      eyebrow="PREFERENCES & GOVERNANCE"
      title="设置"
      description="管理工作区偏好、通知、治理与产品体验设置。"
    >
      <div className="empty-state">
        <h2>Audit & Governance</h2>
        <p>查看组织审计记录、Retention、Legal Hold、数据删除工作流与审计导出。</p>
        <Link className="command-trigger" href="/app/settings/governance">
          打开 Governance Center →
        </Link>
      </div>
    </ShellSection>
  );
}
