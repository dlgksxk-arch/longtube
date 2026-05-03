"use client";

import Link from "next/link";
import { useState } from "react";
import { LogIn } from "lucide-react";
import { authApi } from "@/lib/api";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      await authApi.login(username, password);
      const params = new URLSearchParams(window.location.search);
      window.location.href = params.get("next") || "/oneclick/live";
    } catch (err) {
      setError((err as Error).message || "로그인 실패");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-bg-primary text-white flex items-center justify-center px-4">
      <section className="w-full max-w-md border border-border bg-bg-secondary rounded-lg p-7 shadow-2xl">
        <div className="mb-7">
          <div className="w-12 h-12 rounded-lg bg-accent-primary flex items-center justify-center mb-4">
            <LogIn size={24} />
          </div>
          <h1 className="text-3xl font-bold">LongTube 로그인</h1>
          <p className="mt-2 text-gray-400">승인된 계정만 제작 서버에 접근할 수 있습니다.</p>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <label className="block">
            <span className="text-sm font-semibold text-gray-300">아이디</span>
            <input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              className="mt-2 w-full rounded-md border border-border bg-bg-primary px-4 py-3 outline-none focus:border-accent-primary"
              required
            />
          </label>
          <label className="block">
            <span className="text-sm font-semibold text-gray-300">비밀번호</span>
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              autoComplete="current-password"
              className="mt-2 w-full rounded-md border border-border bg-bg-primary px-4 py-3 outline-none focus:border-accent-primary"
              required
            />
          </label>

          {error && (
            <div className="rounded-md border border-red-500/50 bg-red-500/10 px-4 py-3 text-sm text-red-200">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-md bg-accent-primary px-4 py-3 font-bold hover:bg-purple-600 disabled:opacity-60"
          >
            {loading ? "확인 중..." : "로그인"}
          </button>
        </form>

        <div className="mt-5 flex items-center justify-between text-sm text-gray-400">
          <span>계정이 없으면 승인 요청을 보내세요.</span>
          <Link href="/signup" className="text-accent-primary hover:underline">
            회원가입
          </Link>
        </div>
      </section>
    </main>
  );
}
