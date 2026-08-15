import type { Metadata } from "next";
import Link from "next/link";
import { AuthForm } from "@/components/auth/auth-form";

export const metadata: Metadata = { title: "创建账户" };

export default function SignupPage() {
  return (
    <main className="auth-page">
      <Link className="brand-lockup auth-brand" href="/">
        <span className="brand-mark" aria-hidden="true">
          L
        </span>
        <span>LUMI</span>
      </Link>
      <section className="auth-card">
        <p className="eyebrow">START CREATING</p>
        <h1>创建 LUMI 账户</h1>
        <p>从一个统一工作空间开始你的设计流程。</p>
        <AuthForm mode="signup" />
      </section>
    </main>
  );
}
