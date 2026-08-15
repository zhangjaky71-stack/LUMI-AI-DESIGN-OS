import type { Metadata } from "next";
import Link from "next/link";
import { AuthForm } from "@/components/auth/auth-form";

export const metadata: Metadata = { title: "登录" };

export default function LoginPage() {
  return (
    <main className="auth-page">
      <Link className="brand-lockup auth-brand" href="/">
        <span className="brand-mark" aria-hidden="true">L</span>
        <span>LUMI</span>
      </Link>
      <section className="auth-card">
        <p className="eyebrow">WELCOME BACK</p>
        <h1>登录 LUMI</h1>
        <p>继续进入你的 AI 设计工作空间。</p>
        <AuthForm mode="login" />
      </section>
    </main>
  );
}
