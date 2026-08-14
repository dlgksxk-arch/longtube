"use client";

import { useEffect, useState } from "react";
import { ImagePlus, Loader2, Package, Shirt, Wand2, X } from "lucide-react";
import { assetUrl, imageApi, type ProductEditResult } from "@/lib/api";

interface Props {
  projectId: string;
}

interface ImageInputProps {
  label: string;
  required?: boolean;
  file: File | null;
  disabled?: boolean;
  onChange: (file: File | null) => void;
}

function ImageInput({ label, required, file, disabled, onChange }: ImageInputProps) {
  const [preview, setPreview] = useState("");

  useEffect(() => {
    if (!file) {
      setPreview("");
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  return (
    <label
      className={`relative aspect-[4/3] rounded-lg border border-dashed overflow-hidden flex flex-col items-center justify-center gap-2 transition-colors ${
        disabled
          ? "border-border bg-bg-primary/40 opacity-50 cursor-not-allowed"
          : "border-border bg-bg-primary hover:border-accent-primary/60 cursor-pointer"
      }`}
    >
      <input
        type="file"
        accept="image/png,image/jpeg,image/webp"
        disabled={disabled}
        className="hidden"
        onChange={(event) => onChange(event.target.files?.[0] || null)}
      />
      {preview ? (
        <>
          <img src={preview} alt={label} className="absolute inset-0 w-full h-full object-contain" />
          <button
            type="button"
            className="absolute top-2 right-2 p-1 rounded-full bg-black/70 text-white hover:bg-black"
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              onChange(null);
            }}
            aria-label={`${label} 제거`}
          >
            <X size={13} />
          </button>
        </>
      ) : (
        <>
          <ImagePlus size={22} className="text-gray-500" />
          <span className="text-xs text-gray-400">
            {label}{required ? " *" : " (선택)"}
          </span>
        </>
      )}
    </label>
  );
}

export default function ProductEditPanel({ projectId }: Props) {
  const [modelImage, setModelImage] = useState<File | null>(null);
  const [productImage1, setProductImage1] = useState<File | null>(null);
  const [productImage2, setProductImage2] = useState<File | null>(null);
  const [productName, setProductName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<ProductEditResult | null>(null);

  const handleProduct1 = (file: File | null) => {
    setProductImage1(file);
    if (!file) setProductImage2(null);
  };

  const generate = async () => {
    if (!modelImage) {
      alert("모델 이미지를 넣어주세요.");
      return;
    }
    if (!prompt.trim()) {
      alert("변경할 의상, 배경 또는 제품 사용 방식을 입력하세요.");
      return;
    }
    setGenerating(true);
    setResult(null);
    try {
      const response = await imageApi.productEdit(projectId, {
        modelImage,
        productImage1,
        productImage2,
        productName: productName.trim(),
        prompt: prompt.trim(),
      });
      setResult(response);
    } catch (error: any) {
      alert(`제품 합성 실패: ${error?.message || error}`);
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="bg-bg-secondary border border-border rounded-lg p-5 space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-accent-secondary">
            <Shirt size={18} />
            <h3 className="font-semibold">제품 착용·사용 합성</h3>
          </div>
          <p className="text-xs text-gray-500 mt-1">
            Qwen Image Edit · 모델 + 제품 + 제품 + 프롬프트
          </p>
        </div>
        <div className="text-right text-[11px] text-gray-500 leading-5">
          <div>제품 사진 있음: 착용·사용 합성</div>
          <div>제품 사진 없음: 의상·배경 변경</div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <ImageInput label="모델 이미지" required file={modelImage} onChange={setModelImage} />
        <ImageInput label="제품 이미지 1" file={productImage1} onChange={handleProduct1} />
        <ImageInput
          label="제품 이미지 2"
          file={productImage2}
          disabled={!productImage1}
          onChange={setProductImage2}
        />
      </div>

      <div className="grid grid-cols-[minmax(0,0.7fr)_minmax(0,1.3fr)] gap-3">
        <label className="space-y-1.5">
          <span className="text-xs text-gray-400 flex items-center gap-1.5">
            <Package size={13} /> 제품명 (선택)
          </span>
          <input
            value={productName}
            onChange={(event) => setProductName(event.target.value)}
            placeholder="예: 나이키 에어맥스 90 흰색"
            className="w-full h-10 px-3 rounded-lg bg-bg-primary border border-border text-sm text-white outline-none focus:border-accent-primary"
          />
        </label>
        <label className="space-y-1.5">
          <span className="text-xs text-gray-400">편집 프롬프트 *</span>
          <textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder={
              productImage1
                ? "제품을 자연스럽게 착용하고 전신이 보이게. 배경은 흰색 스튜디오."
                : "검은 정장으로 바꾸고 배경을 밝은 호텔 로비로 변경."
            }
            rows={3}
            className="w-full px-3 py-2 rounded-lg bg-bg-primary border border-border text-sm text-white outline-none resize-y focus:border-accent-primary"
          />
        </label>
      </div>

      <button
        type="button"
        onClick={generate}
        disabled={generating}
        className="w-full h-10 rounded-lg bg-accent-primary text-white text-sm font-semibold flex items-center justify-center gap-2 hover:opacity-90 disabled:opacity-60"
      >
        {generating ? <Loader2 size={16} className="animate-spin" /> : <Wand2 size={16} />}
        {generating ? "Qwen 편집 중..." : "합성 이미지 생성"}
      </button>

      {result && (
        <div className="border border-border rounded-lg overflow-hidden bg-bg-primary">
          <img
            src={`${assetUrl(projectId, result.path)}?t=${Date.now()}`}
            alt="제품 합성 결과"
            className="w-full max-h-[620px] object-contain"
          />
          <div className="px-3 py-2 text-xs text-gray-400 flex items-center justify-between">
            <span>{result.mode === "product_wear_or_use" ? `제품 ${result.product_count}장 적용` : "의상·배경 편집"}</span>
            <span>{result.model}</span>
          </div>
        </div>
      )}
    </div>
  );
}
