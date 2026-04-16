"use client";

import { useState, useEffect } from "react";
import {
  FileText, Wand2, Plus, Trash2, GripVertical, Save, Edit3, X, ChevronDown, ChevronUp
} from "lucide-react";
import LoadingButton from "@/components/common/LoadingButton";
import ModelSelector from "@/components/common/ModelSelector";
import CostEstimate from "@/components/common/CostEstimate";
import { scriptApi, modelsApi, projectsApi, type Project, type Cut, type ModelInfo } from "@/lib/api";
import GenerationTimer from "@/components/common/GenerationTimer";

interface Props {
  project: Project;
  onUpdate: () => void;
  onCutsChange?: (cuts: Cut[]) => void;
}

export default function StepScript({ project, onUpdate, onCutsChange }: Props) {
  const [cuts, setCuts] = useState<Cut[]>([]);
  const [generating, setGenerating] = useState(false);
  const [editingCut, setEditingCut] = useState<number | null>(null);
  const [editNarration, setEditNarration] = useState("");
  const [editPrompt, setEditPrompt] = useState("");
  const [savingCut, setSavingCut] = useState(false);
  const [expandedCut, setExpandedCut] = useState<number | null>(null);
  const [llmModels, setLlmModels] = useState<ModelInfo[]>([]);

  useEffect(() => {
    loadCuts();
    modelsApi.listLLM().then((d) => setLlmModels(d.models)).catch(() => {});
  }, [project.id]);

  const loadCuts = async () => {
    try {
      const data = await scriptApi.listCuts(project.id);
      setCuts(data.cuts || []);
      onCutsChange?.(data.cuts || []);
    } catch {}
  };

  const changeModel = async (modelId: string) => {
    try {
      await projectsApi.update(project.id, { config: { script_model: modelId } });
      onUpdate();
    } catch {}
  };

  const generateScript = async () => {
    setGenerating(true);
    try {
      // v1.1.49: 백그라운드 비동기 생성 — 탭 이동해도 작업 계속 진행
      await scriptApi.generateAsync(project.id);
      onUpdate();
    } catch (err: any) {
      alert("대본 생성 실패: " + err.message);
      setGenerating(false);
    }
    // generating 상태는 GenerationTimer.onComplete 에서 해제
  };

  const startEdit = (cut: Cut) => {
    setEditingCut(cut.cut_number);
    setEditNarration(cut.narration);
    setEditPrompt(cut.image_prompt);
  };

  const cancelEdit = () => {
    setEditingCut(null);
  };

  const saveEdit = async () => {
    if (editingCut === null) return;
    setSavingCut(true);
    try {
      await scriptApi.editCut(project.id, editingCut, {
        narration: editNarration,
        image_prompt: editPrompt,
      });
      setCuts((prev) =>
        prev.map((c) =>
          c.cut_number === editingCut
            ? { ...c, narration: editNarration, image_prompt: editPrompt }
            : c
        )
      );
      setEditingCut(null);
      onUpdate();
    } catch (err: any) {
      alert("저장 실패: " + err.message);
    } finally {
      setSavingCut(false);
    }
  };

  const deleteCut = async (cutNumber: number) => {
    if (!confirm(`컷 ${cutNumber}을 삭제하시겠습니까?`)) return;
    try {
      await scriptApi.deleteCut(project.id, cutNumber);
      setCuts((prev) => prev.filter((c) => c.cut_number !== cutNumber));
      onUpdate();
    } catch (err: any) {
      alert("삭제 실패: " + err.message);
    }
  };

  const addCut = async () => {
    const newNum = cuts.length > 0 ? Math.max(...cuts.map((c) => c.cut_number)) + 1 : 1;
    try {
      const result = await scriptApi.addCut(project.id, {
        cut_number: newNum,
        narration: "새 나레이션을 입력하세요.",
        image_prompt: "A cinematic scene...",
        scene_type: "narration",
      });
      setCuts((prev) => [...prev, { ...result, cut_number: result.cut_number }]);
      onUpdate();
    } catch (err: any) {
      alert("추가 실패: " + err.message);
    }
  };

  const totalDuration = cuts.reduce((sum, c) => sum + (c.duration_estimate || 5), 0);
  const cutCount = cuts.length || Math.floor(project.config.target_duration / 5);

  // LLM cost estimate: ~1K input tokens (prompt) + ~200 output tokens per cut
  const selectedModel = llmModels.find((m) => m.id === project.config.script_model);
  const inputCost = (selectedModel?.cost_input || 3) / 1_000_000;
  const outputCost = (selectedModel?.cost_output || 15) / 1_000_000;
  const estimatedScriptCost = (2000 * inputCost) + (cutCount * 150 * outputCost);

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* ── 상단 컨트롤 (틀고정) ── */}
      <div className="flex-shrink-0 space-y-4 pb-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-accent-secondary">
          <FileText size={20} />
          <h2 className="text-lg font-semibold">대본 / 컷 구성</h2>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-400">
            {cuts.length}컷 · 약 {Math.round(totalDuration / 60)}분
          </span>
          <LoadingButton onClick={generateScript} loading={generating} icon={<Wand2 size={14} />} variant="secondary">
            {cuts.length > 0 ? "대본 재생성" : "대본 생성"}
          </LoadingButton>
          {cuts.length > 0 && !generating && (
            <button
              onClick={async () => {
                if (!confirm(
                  `대본 ${cuts.length}컷을 모두 삭제하고 초기 상태로 되돌립니다.\n` +
                  `이 프로젝트의 이후 단계(음성, 이미지, 영상, 자막) 결과도 같이 정리됩니다.\n계속할까요?`
                )) return;
                try {
                  // 대본을 지우면 이후 단계의 결과도 유효하지 않으므로 같이 초기화.
                  await scriptApi.clearStep(project.id, "subtitle").catch(() => {});
                  await scriptApi.clearStep(project.id, "video").catch(() => {});
                  await scriptApi.clearStep(project.id, "image").catch(() => {});
                  await scriptApi.clearStep(project.id, "voice").catch(() => {});
                  await scriptApi.clearStep(project.id, "script");
                  setCuts([]);
                  onCutsChange?.([]);
                  onUpdate();
                } catch (err: any) {
                  alert("초기화 실패: " + (err?.message || err));
                }
              }}
              title="대본 초기화 (컷 전체 삭제)"
              className="p-2 rounded-lg border border-border text-gray-500 hover:text-accent-danger hover:border-accent-danger/50 transition-colors"
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Model selector + language + cost */}
      <div className="grid grid-cols-3 gap-3">
        <ModelSelector
          label="대본 생성 모델"
          models={llmModels}
          value={project.config.script_model}
          onChange={changeModel}
        />
        <div>
          <label className="block text-xs text-gray-400 mb-1">대본 언어</label>
          <select
            value={project.config.language || "ko"}
            onChange={async (e) => {
              try {
                await projectsApi.update(project.id, { config: { language: e.target.value } });
                onUpdate();
              } catch {}
            }}
            className="w-full bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
          >
            <option value="ko">🇰🇷 한국어</option>
            <option value="en">🇺🇸 English</option>
            <option value="ja">🇯🇵 日本語</option>
          </select>
        </div>
        <div className="flex items-end">
          <CostEstimate
            label="대본 예상 비용"
            amount={estimatedScriptCost}
            detail={`${cutCount}컷 기준`}
          />
        </div>
      </div>

      {/* Generation timer — v1.1.49: 비동기 백그라운드 생성 (탭 이동해도 진행) */}
      <GenerationTimer
        projectId={project.id}
        step="script"
        label="대본 생성 중..."
        onComplete={() => {
          setGenerating(false);
          loadCuts();
          onUpdate();
        }}
      />
      </div>{/* 상단 컨트롤 끝 */}

      {/* ── 스크롤 영역 ── */}
      <div className="flex-1 overflow-y-auto min-h-0">
      {cuts.length === 0 ? (
        <div className="bg-bg-secondary border border-border rounded-lg p-12 text-center">
          <FileText size={48} className="mx-auto mb-4 text-gray-600" />
          <p className="text-gray-400 mb-4">아직 대본이 없습니다. 위의 버튼을 눌러 AI로 생성하세요.</p>
          <p className="text-xs text-gray-600">설정 탭에서 LLM 모델과 스타일을 먼저 확인하세요.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {cuts.map((cut) => (
            <div
              key={cut.cut_number}
              className="bg-bg-secondary border border-border rounded-lg overflow-hidden"
            >
              {/* Header */}
              <div
                className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-bg-tertiary/50 transition-colors"
                onClick={() => setExpandedCut(expandedCut === cut.cut_number ? null : cut.cut_number)}
              >
                <GripVertical size={14} className="text-gray-600" />
                <div className="w-7 h-7 rounded-full bg-accent-primary/20 text-accent-primary flex items-center justify-center text-xs font-bold">
                  {cut.cut_number}
                </div>
                <span className="text-xs px-2 py-0.5 rounded bg-bg-tertiary text-gray-400">{cut.scene_type}</span>
                <p className="flex-1 text-sm text-gray-300 truncate">{cut.narration}</p>
                <div className="flex items-center gap-1">
                  <button
                    onClick={(e) => { e.stopPropagation(); startEdit(cut); }}
                    className="p-1.5 rounded hover:bg-accent-primary/20 text-gray-400 hover:text-accent-primary transition-colors"
                  >
                    <Edit3 size={14} />
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); deleteCut(cut.cut_number); }}
                    className="p-1.5 rounded hover:bg-accent-danger/20 text-gray-400 hover:text-accent-danger transition-colors"
                  >
                    <Trash2 size={14} />
                  </button>
                  {expandedCut === cut.cut_number ? <ChevronUp size={14} className="text-gray-500" /> : <ChevronDown size={14} className="text-gray-500" />}
                </div>
              </div>

              {/* Expanded content or edit mode */}
              {editingCut === cut.cut_number ? (
                <div className="px-4 pb-4 space-y-3 border-t border-border pt-3">
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">나레이션</label>
                    <textarea
                      value={editNarration}
                      onChange={(e) => setEditNarration(e.target.value)}
                      rows={4}
                      className="w-full bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent-primary resize-y"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">이미지 프롬프트</label>
                    <textarea
                      value={editPrompt}
                      onChange={(e) => setEditPrompt(e.target.value)}
                      rows={3}
                      className="w-full bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent-primary resize-y"
                    />
                  </div>
                  <div className="flex items-center gap-2 justify-end">
                    <button onClick={cancelEdit} className="px-3 py-1.5 text-sm text-gray-400 hover:text-white">
                      <X size={14} className="inline mr-1" />취소
                    </button>
                    <LoadingButton onClick={saveEdit} loading={savingCut} icon={<Save size={14} />} variant="primary" className="!py-1.5">
                      저장
                    </LoadingButton>
                  </div>
                </div>
              ) : expandedCut === cut.cut_number ? (
                <div className="px-4 pb-4 space-y-2 border-t border-border pt-3">
                  <div>
                    <span className="text-xs text-gray-500">나레이션</span>
                    <p className="text-sm text-gray-200 mt-1 whitespace-pre-wrap">{cut.narration}</p>
                  </div>
                  <div>
                    <span className="text-xs text-gray-500">이미지 프롬프트</span>
                    <p className="text-sm text-gray-400 mt-1 italic">{cut.image_prompt}</p>
                  </div>
                </div>
              ) : null}
            </div>
          ))}

          {/* Add cut button */}
          <button
            onClick={addCut}
            className="w-full border border-dashed border-border rounded-lg py-3 text-sm text-gray-500 hover:text-accent-primary hover:border-accent-primary/50 transition-colors flex items-center justify-center gap-2"
          >
            <Plus size={14} /> 컷 추가
          </button>
        </div>
      )}
      </div>{/* 스크롤 영역 끝 */}
    </div>
  );
}
