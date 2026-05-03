"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Check, RefreshCw, Shield, X } from "lucide-react";
import { authApi, type AuthUser } from "@/lib/api";

export default function AdminUsersPage() {
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      setUsers(await authApi.pendingUsers());
    } catch (err) {
      setError((err as Error).message || "승인 대기 목록을 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const approve = async (id: string) => {
    await authApi.approveUser(id, "user");
    await load();
  };

  const reject = async (id: string) => {
    await authApi.rejectUser(id);
    await load();
  };

  return (
    <main className="min-h-screen bg-bg-primary text-white">
      <div className="max-w-4xl mx-auto p-8">
        <div className="flex items-center justify-between mb-8">
          <div>
            <div className="flex items-center gap-3">
              <Shield className="text-accent-primary" size={26} />
              <h1 className="text-3xl font-bold">계정 승인</h1>
            </div>
            <p className="mt-2 text-gray-400">회원가입 요청은 여기서 승인해야 로그인할 수 있습니다.</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={load}
              className="rounded-md border border-border px-4 py-2 text-sm hover:bg-bg-secondary"
            >
              <RefreshCw size={15} className={`inline mr-2 ${loading ? "animate-spin" : ""}`} />
              새로고침
            </button>
            <Link href="/oneclick/live" className="rounded-md bg-accent-primary px-4 py-2 text-sm font-bold">
              돌아가기
            </Link>
          </div>
        </div>

        {error && (
          <div className="mb-4 rounded-md border border-red-500/50 bg-red-500/10 px-4 py-3 text-red-200">
            {error}
          </div>
        )}

        <section className="border border-border bg-bg-secondary rounded-lg overflow-hidden">
          {users.length === 0 ? (
            <div className="p-8 text-gray-400">승인 대기 계정이 없습니다.</div>
          ) : (
            users.map((user) => (
              <div key={user.id} className="flex items-center justify-between gap-4 border-b border-border last:border-b-0 p-4">
                <div className="min-w-0">
                  <div className="font-bold text-lg">{user.display_name || user.username}</div>
                  <div className="text-sm text-gray-400">
                    {user.username} · {user.created_at ? new Date(user.created_at).toLocaleString("ko-KR") : "요청 시각 없음"}
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => approve(user.id)}
                    className="rounded-md bg-green-600 px-3 py-2 text-sm font-bold hover:bg-green-500"
                  >
                    <Check size={15} className="inline mr-1" />
                    승인
                  </button>
                  <button
                    onClick={() => reject(user.id)}
                    className="rounded-md border border-red-500/50 px-3 py-2 text-sm text-red-200 hover:bg-red-500/10"
                  >
                    <X size={15} className="inline mr-1" />
                    거절
                  </button>
                </div>
              </div>
            ))
          )}
        </section>
      </div>
    </main>
  );
}
