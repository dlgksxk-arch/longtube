"use client";

import { useEffect, useState } from "react";
import { AlertCircle, GitBranch, RefreshCw, Wand2 } from "lucide-react";
import LoadingButton from "@/components/common/LoadingButton";
import ModelSelector from "@/components/common/ModelSelector";
import CostEstimate from "@/components/common/CostEstimate";
import GenerationTimer from "@/components/common/GenerationTimer";
import {
  modelsApi,
  projectsApi,
  scriptApi,
  taskApi,
  type ModelInfo,
  type Project,
  type StoryPlan,
} from "@/lib/api";

const SCRIPT_STORY_BLOCK_CUTS = 10;
const SCRIPT_STORY_BLOCK_TOTAL = 15;

interface Props {
  project: Project;
  onUpdate: () => void;
}

function lines(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item || "").trim()).filter(Boolean);
  }
  const text = String(value || "").trim();
  return text ? [text] : [];
}

function storyCharacterFirstBlock(item: { first_appearance_block?: string | number; first_appearance_cut?: string } = {}) {
  const explicit = Number(item.first_appearance_block || 0);
  if (Number.isFinite(explicit) && explicit > 0) return `Block ${explicit}`;
  const match = String(item.first_appearance_cut || "").match(/\d+/);
  if (!match) return "-";
  const cut = Number(match[0]);
  return Number.isFinite(cut) && cut > 0 ? `Block ${Math.ceil(cut / SCRIPT_STORY_BLOCK_CUTS)}` : "-";
}

export default function StepStory({ project, onUpdate }: Props) {
  const [plan, setPlan] = useState<StoryPlan | null>(null);
  const [exists, setExists] = useState(false);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [llmModels, setLlmModels] = useState<ModelInfo[]>([]);

  const storyModel = project.config.story_model || project.config.script_model;

  useEffect(() => {
    loadStoryPlan();
    modelsApi.listLLM().then((d) => setLlmModels(d.models || [])).catch(() => {});
  }, [project.id]);

  const loadStoryPlan = async () => {
    setLoading(true);
    try {
      const data = await scriptApi.getStoryPlan(project.id);
      setExists(Boolean(data.exists));
      setPlan(data.story_plan || null);
    } catch {
      setExists(false);
      setPlan(null);
    } finally {
      setLoading(false);
    }
  };

  const changeModel = async (modelId: string) => {
    try {
      await projectsApi.update(project.id, { config: { story_model: modelId } });
      onUpdate();
    } catch {}
  };

  const generateStoryPlan = async () => {
    setGenerating(true);
    try {
      await scriptApi.generateStoryPlanAsync(project.id);
      onUpdate();
      for (let i = 0; i < 180; i += 1) {
        await new Promise((resolve) => setTimeout(resolve, 1500));
        const status = await taskApi.status(project.id, "story").catch(() => null);
        if (status?.status === "failed" || status?.status === "cancelled") {
          alert("스토리 설계 실패: " + (status.error || status.status));
          setGenerating(false);
          onUpdate();
          return;
        }
        if (status?.status === "completed" || status?.status === "idle") {
          await loadStoryPlan();
          setGenerating(false);
          onUpdate();
          return;
        }
      }
      await loadStoryPlan();
    } catch (err: any) {
      alert("스토리 설계 실패: " + err.message);
    } finally {
      setGenerating(false);
    }
  };

  const clearStoryPlan = async () => {
    if (!confirm("스토리 설계 결과를 초기화하시겠습니까?")) return;
    try {
      await scriptApi.clearStep(project.id, "story");
      setExists(false);
      setPlan(null);
      onUpdate();
    } catch (err: any) {
      alert("초기화 실패: " + err.message);
    }
  };

  const selectedModel = llmModels.find((m) => m.id === storyModel);
  const inputCost = (selectedModel?.cost_input || 3) / 1_000_000;
  const outputCost = (selectedModel?.cost_output || 15) / 1_000_000;
  const targetCuts = project.total_cuts || project.estimate?.estimated_cuts || 150;
  const estimatedStoryCost = 4500 * inputCost + (targetCuts >= 100 ? 9500 : 4800) * outputCost;
  const blocks = Array.isArray(plan?.scene_blocks) ? plan.scene_blocks : [];
  const characters = Array.isArray(plan?.character_map) ? plan.character_map : [];
  const causality = lines(plan?.causality_chain);
  const expectedBlocks = Math.ceil(targetCuts / SCRIPT_STORY_BLOCK_CUTS) || SCRIPT_STORY_BLOCK_TOTAL;

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="flex-shrink-0 space-y-4 pb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-accent-secondary">
            <GitBranch size={20} />
            <h2 className="text-lg font-semibold">스토리 설계</h2>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-400">
              {exists ? `${blocks.length}/${expectedBlocks}블럭 · ${SCRIPT_STORY_BLOCK_CUTS}컷/블럭` : "결과 없음"}
            </span>
            <LoadingButton onClick={generateStoryPlan} loading={generating} icon={<Wand2 size={14} />} variant="secondary">
              {exists ? "스토리 재생성" : "스토리 생성"}
            </LoadingButton>
            {exists && !generating && (
              <button
                onClick={clearStoryPlan}
                title="스토리 설계 초기화"
                className="p-2 rounded-lg border border-border text-gray-500 hover:text-accent-danger hover:border-accent-danger/50 transition-colors"
              >
                <RefreshCw size={14} />
              </button>
            )}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <ModelSelector
            label="스토리 설계 모델"
            models={llmModels}
            value={storyModel}
            onChange={changeModel}
          />
          <CostEstimate
            label="스토리 예상 비용"
            amount={estimatedStoryCost}
            detail={`${targetCuts}컷 · ${expectedBlocks}블럭 기준`}
          />
        </div>

        <GenerationTimer
          projectId={project.id}
          step="story"
          label="스토리 설계 중..."
          onComplete={() => {
            setGenerating(false);
            loadStoryPlan();
            onUpdate();
          }}
        />
      </div>

      <div className="flex-1 overflow-y-auto min-h-0">
        {loading ? (
          <div className="text-sm text-gray-500 py-8">불러오는 중...</div>
        ) : !plan ? (
          <div className="bg-bg-secondary border border-border rounded-lg p-12 text-center">
            <AlertCircle size={42} className="mx-auto mb-4 text-gray-600" />
            <p className="text-gray-400 mb-2">생성된 스토리 설계가 없습니다.</p>
            <p className="text-xs text-gray-600">대본 생성 전 이 단계에서 중심 질문, 답변, 블럭 구조를 먼저 확정합니다.</p>
          </div>
        ) : (
          <div className="space-y-4">
            {characters.length > 0 && (
              <section className="bg-bg-secondary border border-border rounded-lg overflow-hidden">
                <div className="flex items-center justify-between px-4 py-3 border-b border-border">
                  <h3 className="text-sm font-medium text-gray-300">인물 설계</h3>
                  <span className="text-xs text-gray-500">{Math.min(characters.length, 4)}개</span>
                </div>
                <div className="grid grid-cols-2 gap-3 p-4">
                  {characters.slice(0, 4).map((item, idx) => (
                    <div key={`${item.name || "character"}-${idx}`} className="bg-bg-primary border border-border rounded-lg p-3">
                      <div className="text-sm font-semibold text-gray-100">{item.name || `인물 ${idx + 1}`}</div>
                      <div className="mt-2 space-y-1 text-xs leading-5 text-gray-400">
                        <div>설명: {item.identity || item.first_appearance_explanation || "-"}</div>
                        <div>첫출현 블럭: {storyCharacterFirstBlock(item)}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {causality.length > 0 && (
              <section className="bg-bg-secondary border border-border rounded-lg overflow-hidden">
                <div className="flex items-center justify-between px-4 py-3 border-b border-border">
                  <h3 className="text-sm font-medium text-gray-300">사건 인과</h3>
                  <span className="text-xs text-gray-500">{causality.length}단계</span>
                </div>
                <ol className="space-y-2 p-4 text-sm leading-6 text-gray-200">
                  {causality.map((line, idx) => (
                    <li key={`${line}-${idx}`} className="flex gap-2">
                      <span className="shrink-0 font-mono text-xs text-gray-500">{String(idx + 1).padStart(2, "0")}</span>
                      <span>{line}</span>
                    </li>
                  ))}
                </ol>
              </section>
            )}

            <section className="bg-bg-secondary border border-border rounded-lg overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b border-border">
                <h3 className="text-sm font-medium text-gray-300">블럭별 흐름</h3>
                <span className="text-xs text-gray-500">{blocks.length}/{expectedBlocks}개 · {SCRIPT_STORY_BLOCK_CUTS}컷/블럭</span>
              </div>
              <div className="divide-y divide-border">
                {blocks.map((block, idx) => (
                  <div key={`${block.block_id || idx}`} className="p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="w-7 h-7 rounded-full bg-accent-primary/20 text-accent-primary flex items-center justify-center text-xs font-bold">
                        {block.block_id || idx + 1}
                      </span>
                      <span className="text-xs px-2 py-0.5 rounded bg-bg-tertiary text-gray-400">
                        {block.cut_range || "-"}
                      </span>
                      <span className="text-xs px-2 py-0.5 rounded bg-accent-secondary/10 text-accent-secondary">
                        {block.block_role || "-"}
                      </span>
                    </div>
                    <p className="text-sm text-gray-200 leading-relaxed mb-2">{block.block_goal || block.new_information || "-"}</p>
                    <div className="grid grid-cols-2 gap-3 text-xs">
                      <div className="text-gray-400">
                        <span className="text-gray-500">{Number(block.block_id || 0) === 1 ? "질문: " : "핵심: "}</span>
                        {block.mini_question || "-"}
                      </div>
                      <div className="text-gray-400">
                        <span className="text-gray-500">인과: </span>
                        {block.continuity_from_previous || "-"}
                      </div>
                      <div className="text-gray-400">
                        <span className="text-gray-500">압박: </span>
                        {block.tension || "-"}
                      </div>
                      <div className="text-gray-400">
                        <span className="text-gray-500">전환: </span>
                        {block.turn || block.turn_to_next || "-"}
                      </div>
                      {lines(block.key_facts).length > 0 && (
                        <div className="col-span-2 text-gray-400">
                          <span className="text-gray-500">사실: </span>
                          {lines(block.key_facts).join(" / ")}
                        </div>
                      )}
                      {lines(block.required_script_moves).length > 0 && (
                        <div className="col-span-2 text-gray-400">
                          <span className="text-gray-500">대본 지시: </span>
                          {lines(block.required_script_moves).join(" / ")}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
