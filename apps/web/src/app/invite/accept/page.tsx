import Link from "next/link";

export default function InviteAcceptPage() {
  return (
    <main className="simple-state-page">
      <p className="eyebrow">ORGANIZATION INVITE</p>
      <h1>接受组织邀请</h1>
      <p>
        邀请验证与成员写入将由 NODE-16
        认证与租户运行时完成。当前入口不会在客户端自行信任邀请参数，也不会伪造成员关系。
      </p>
      <Link className="secondary-button" href="/login">
        前往登录
      </Link>
    </main>
  );
}
