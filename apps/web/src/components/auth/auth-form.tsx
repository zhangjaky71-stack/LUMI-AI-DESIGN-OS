"use client";

import Link from "next/link";
import { useState } from "react";

export function AuthForm({ mode }: Readonly<{ mode: "login" | "signup" }>) {
  const [message, setMessage] = useState<string | null>(null);
  const isLogin = mode === "login";

  return (
    <form
      className="auth-form"
      onSubmit={(event) => {
        event.preventDefault();
        setMessage("当前无法完成此请求，请稍后再试。");
      }}
    >
      <div>
        <label htmlFor="email">邮箱</label>
        <input id="email" name="email" type="email" autoComplete="email" required />
      </div>
      <div>
        <label htmlFor="password">密码</label>
        <input id="password" name="password" type="password" autoComplete={isLogin ? "current-password" : "new-password"} minLength={8} required />
      </div>
      <button className="primary-button" type="submit">{isLogin ? "登录" : "创建账户"}</button>
      {message ? <p className="auth-message" role="status">{message}</p> : null}
      <p className="auth-switch">
        {isLogin ? "还没有账户？" : "已有账户？"}{" "}
        <Link href={isLogin ? "/signup" : "/login"}>{isLogin ? "注册" : "登录"}</Link>
      </p>
    </form>
  );
}
