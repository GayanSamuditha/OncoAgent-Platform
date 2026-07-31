import type { Metadata } from "next";

import "./globals.css";
import AuthGate from "./components/auth-gate";

export const metadata: Metadata = {
  title: "OncoAgent Platform",
  description: "Governed synthetic-data agent platform foundation",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body><AuthGate>{children}</AuthGate></body>
    </html>
  );
}
