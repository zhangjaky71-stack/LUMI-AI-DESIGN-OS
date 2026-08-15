import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "LUMI AI Design OS", template: "%s · LUMI" },
  description: "AI-native design operating system",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
