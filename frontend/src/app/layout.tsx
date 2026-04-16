import type { Metadata } from "next";
import "./globals.css";
import Providers from "@/components/common/Providers";

export const metadata: Metadata = {
  title: "LongTube",
  description: "YouTube longform video automation pipeline",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="bg-bg-primary text-white min-h-screen">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
