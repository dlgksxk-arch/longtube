"use client";

import Link from "next/link";
import { useState } from "react";
import { UserPlus } from "lucide-react";
import { authApi } from "@/lib/api";

export default function SignupPage() {
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setMessage("");
    setLoading(true);
    try {
      const user = await authApi.signup({
        username,
        password,
        display_name: displayName || username,
      });
      if (user.status === "approved") {
        window.location.href = "/oneclick/live";
        return;
      }
      setMessage("가입 요청이 접수됐습니다. 마스터 승인 후 로그인할 수 있습니다.");
      setUsername("");
      setDisplayName("");
      setPassword("");
    } catch (err) {
      setError((err as Error).message || "회원가입 실패");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-bg-primary text-white flex items-center justify-center px-4">
      <section className="w-full max-w-md border border-border bg-bg-secondary rounded-lg p-7 shadow-2xl">
        <div className="mb-7">
          <div className="w-12 h-12 rounded-lg bg-accent-primary flex items-center justify-center mb-4">
            <UserPlus size={24} />
          </div>
          <h1 className="text-3xl font-bold">회원가입 요청</h1>
          <p className="mt-2 text-gray-400">새 계정은 마스터 승인 전까지 대기 상태로 유지됩니다.</p>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <label className="block">
            <span className="text-sm font-semibold text-gray-300">아이디</span>
            <input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              pattern="[A-Za-z0-9_.-]{3,40}"
              className="mt-2 w-full rounded-md border border-border bg-bg-primary px-4 py-3 outline-none focus:border-accent-primary"
              required
            />
          </label>
          <label className="block">
            <span className="text-sm font-semibold text-gray-300">표시 이름</span>
            <input
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              className="mt-2 w-full rounded-md border border-border bg-bg-primary px-4 py-3 outline-none focus:border-accent-primary"
            />
          </label>
          <label className="block">
            <span className="text-sm font-semibold text-gray-300">비밀번호</span>
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              minLength={8}
              autoComplete="new-password"
              className="mt-2 w-full rounded-md border border-border bg-bg-primary px-4 py-3 outline-none focus:border-accent-primary"
              required
            />
          </label>

          {message && (
            <div className="rounded-md border border-green-500/50 bg-green-500/10 px-4 py-3 text-sm text-green-200">
              {message}
            </div>
          )}
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
            {loading ? "요청 중..." : "승인 요청"}
          </button>
        </form>

        <div className="mt-5 text-right text-sm">
          <Link href="/login" className="text-accent-primary hover:underline">
            로그인으로 돌아가기
          </Link>
        </div>
      </section>
    </main>
  );
}
