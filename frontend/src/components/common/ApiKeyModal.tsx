"use client";

import { useState, useEffect } from "react";
import { X, ExternalLink, Eye, EyeOff, Save, Trash2, CheckCircle, AlertCircle } from "lucide-react";
import { apiKeysApi, type ProviderInfo } from "@/lib/api";

interface Props {
  provider: string;  // provider name from API status
  balanceUrl?: string;  // URL to check balance
  onClose: () => void;
  onSaved: () => void;
}

// Provider → key creation URL (fallback, also fetched from backend)
const PROVIDER_URLS: Record<string, string> = {
  "Anthropic": "https://console.anthropic.com/settings/keys",
  "OpenAI": "https://platform.openai.com/api-keys",
  "ElevenLabs": "https://elevenlabs.io/app/settings/api-keys",
  "fal.ai": "https://fal.ai/dashboard/keys",
  "xAI (Grok)": "https://console.x.ai/",
  "Kling": "https://klingai.com/",
  "Replicate": "https://replicate.com/account/api-tokens",
  "Replicate (fal/NanoBanana)": "https://replicate.com/account/api-tokens",
  "Runway": "https://app.runwayml.com/settings/api-keys",
  "Midjourney": "https://www.midjourney.com/account",
};

export default function ApiKeyModal({ provider, balanceUrl, onClose, onSaved }: Props) {
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [providerInfo, setProviderInfo] = useState<ProviderInfo | null>(null);
  const [status, setStatus] = useState<"idle" | "success" | "error">("idle");
  const [statusMsg, setStatusMsg] = useState("");

  useEffect(() => {
    apiKeysApi.listProviders().then((data) => {
      const found = data.providers.find((p) => p.provider === provider);
      if (found) setProviderInfo(found);
    }).catch(() => {});
  }, [provider]);

  const keyUrl = providerInfo?.url || PROVIDER_URLS[provider] || "";

  const handleSave = async () => {
    if (!apiKey.trim()) return;
    setSaving(true);
    setStatus("idle");
    try {
      await apiKeysApi.save(provider, apiKey.trim());
      setStatus("success");
      setStatusMsg("저장 완료! 서버에 즉시 반영됩니다.");
      setTimeout(() => {
        onSaved();
        onClose();
      }, 800);
    } catch (err: any) {
      setStatus("error");
      setStatusMsg("저장 실패: " + (err.message || "Unknown error"));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`${provider} API 키를 삭제하시겠습니까?`)) return;
    try {
      await apiKeysApi.remove(provider);
      setStatus("success");
      setStatusMsg("삭제 완료!");
      setTimeout(() => {
        onSaved();
        onClose();
      }, 800);
    } catch (err: any) {
      setStatus("error");
      setStatusMsg("삭제 실패: " + (err.message || "Unknown error"));
    }
  };

  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-bg-secondary border border-border rounded-xl w-full max-w-md shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h3 className="text-base font-bold text-white">{provider} API 키 설정</h3>
          <button onClick={onClose} className="p-1 rounded hover:bg-bg-tertiary text-gray-400 hover:text-white transition-colors">
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-4">
          {/* Current key info */}
          {providerInfo?.has_key && (
            <div className="flex items-center gap-2 text-sm">
              <CheckCircle size={14} className="text-green-400" />
              <span className="text-gray-300">현재 키: <code className="text-gray-400">{providerInfo.masked_key}</code></span>
            </div>
          )}

          {/* Key input */}
          <div>
            <label className="block text-xs text-gray-400 mb-1.5">API Key</label>
            <div className="relative">
              <input
                type={showKey ? "text" : "password"}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSave()}
                placeholder={providerInfo?.has_key ? "새 키로 교체하려면 입력..." : "API 키를 입력하세요"}
                className="w-full bg-bg-primary border border-border rounded-lg px-3 py-2.5 pr-10 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-accent-primary font-mono"
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500 hover:text-gray-300"
              >
                {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>

          {/* Links */}
          <div className="space-y-1.5">
            {keyUrl && (
              <a
                href={keyUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 text-xs text-accent-primary hover:text-purple-300 transition-colors"
              >
                <ExternalLink size={12} />
                {provider} API 키 발급 페이지
              </a>
            )}
            {balanceUrl && (
              <a
                href={balanceUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 text-xs text-green-400 hover:text-green-300 transition-colors"
              >
                <ExternalLink size={12} />
                잔액/사용량 확인 페이지
              </a>
            )}
          </div>

          {/* Status message */}
          {status !== "idle" && (
            <div className={`flex items-center gap-2 text-sm ${status === "success" ? "text-green-400" : "text-red-400"}`}>
              {status === "success" ? <CheckCircle size={14} /> : <AlertCircle size={14} />}
              {statusMsg}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-5 py-3 border-t border-border">
          <div>
            {providerInfo?.has_key && (
              <button
                onClick={handleDelete}
                className="flex items-center gap-1.5 text-xs text-red-400 hover:text-red-300 transition-colors"
              >
                <Trash2 size={12} />
                키 삭제
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors"
            >
              취소
            </button>
            <button
              onClick={handleSave}
              disabled={saving || !apiKey.trim()}
              className="flex items-center gap-1.5 bg-accent-primary hover:bg-purple-600 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Save size={14} />
              {saving ? "저장 중..." : "저장"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
