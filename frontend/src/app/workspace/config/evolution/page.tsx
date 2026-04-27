"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ActivityIcon,
  CheckCircleIcon,
  DnaIcon,
  GaugeIcon,
  XCircleIcon,
  ZapIcon,
} from "lucide-react";
import { useMemo, useState, useEffect } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getJSON } from "@/core/api/http";
import {
  useEvolutionConfig,
  useHealthReports,
  useQualityMetrics,
  useUpdateEvolutionConfig,
  useRegisterEvolutionSkill,
} from "@/core/evolution/hooks";
import { useI18n } from "@/core/i18n/hooks";

interface TrustScoreEntry {
  skill: string;
  total: number;
  successes: number;
  success_rate: number;
  p95_latency_ms: number;
  trust_score: number;
}

interface TrustScoresResponse {
  enabled?: boolean;
  window?: number;
  entries?: TrustScoreEntry[];
}

const TRUST_SCORES_I18N: Record<
  string,
  {
    tabLabel: string;
    observationOn: string;
    observationOff: string;
    windowLabel: string;
    disabledHint: string;
    emptyHint: string;
    tableSkill: string;
    tableTotal: string;
    tableSuccessRate: string;
    tableP95: string;
    tableTrust: string;
    footer: string;
  }
> = {
  "en-US": {
    tabLabel: "Trust Scores",
    observationOn: "observation: on",
    observationOff: "observation: off",
    windowLabel: "window",
    disabledHint:
      "Trust-score observer is disabled. Set SKILL_TRUST_OBSERVATION_ENABLED=1 on the gateway to collect shadow metrics.",
    emptyHint: "Observer enabled but no executions captured in this window yet.",
    tableSkill: "Skill",
    tableTotal: "Total",
    tableSuccessRate: "Success rate",
    tableP95: "p95 latency (ms)",
    tableTrust: "Trust score",
    footer: "Observation-only. No skill enable/disable decisions are made from this data.",
  },
  "zh-CN": {
    tabLabel: "信任评分",
    observationOn: "观察态：开启",
    observationOff: "观察态：关闭",
    windowLabel: "窗口",
    disabledHint:
      "信任评分观察器未启用。请在网关上设置 SKILL_TRUST_OBSERVATION_ENABLED=1 以采集影子指标。",
    emptyHint: "观察器已启用，但此窗口内暂无执行记录。",
    tableSkill: "技能",
    tableTotal: "总数",
    tableSuccessRate: "成功率",
    tableP95: "p95 延迟 (ms)",
    tableTrust: "信任分",
    footer: "仅观察态。该数据不会触发技能启用/禁用决策。",
  },
  "zh-TW": {
    tabLabel: "信任評分",
    observationOn: "觀察態：開啟",
    observationOff: "觀察態：關閉",
    windowLabel: "視窗",
    disabledHint:
      "信任評分觀察器未啟用。請在閘道上設定 SKILL_TRUST_OBSERVATION_ENABLED=1 以採集影子指標。",
    emptyHint: "觀察器已啟用，但此視窗內暫無執行記錄。",
    tableSkill: "技能",
    tableTotal: "總數",
    tableSuccessRate: "成功率",
    tableP95: "p95 延遲 (ms)",
    tableTrust: "信任分",
    footer: "僅觀察態。該資料不會觸發技能啟用/停用決策。",
  },
  ja: {
    tabLabel: "信頼スコア",
    observationOn: "観測モード: 有効",
    observationOff: "観測モード: 無効",
    windowLabel: "ウィンドウ",
    disabledHint:
      "信頼スコアオブザーバーは無効です。ゲートウェイで SKILL_TRUST_OBSERVATION_ENABLED=1 を設定してシャドウメトリクスを収集してください。",
    emptyHint: "オブザーバーは有効ですが、このウィンドウではまだ実行が記録されていません。",
    tableSkill: "スキル",
    tableTotal: "合計",
    tableSuccessRate: "成功率",
    tableP95: "p95 レイテンシ (ms)",
    tableTrust: "信頼スコア",
    footer: "観測のみ。このデータからスキル有効化/無効化の判断は行いません。",
  },
  ko: {
    tabLabel: "신뢰 점수",
    observationOn: "관찰 모드: 켜짐",
    observationOff: "관찰 모드: 꺼짐",
    windowLabel: "윈도우",
    disabledHint:
      "신뢰 점수 관찰자가 비활성화되어 있습니다. 게이트웨이에서 SKILL_TRUST_OBSERVATION_ENABLED=1 을 설정하여 섀도우 메트릭을 수집하세요.",
    emptyHint: "관찰자가 활성화되어 있지만 이 윈도우 내에 실행 기록이 없습니다.",
    tableSkill: "스킬",
    tableTotal: "총 횟수",
    tableSuccessRate: "성공률",
    tableP95: "p95 지연 (ms)",
    tableTrust: "신뢰 점수",
    footer: "관찰 전용. 이 데이터로부터 스킬 활성화/비활성화 결정을 내리지 않습니다.",
  },
};

export default function EvolutionConfigPage() {
  const { t, locale } = useI18n();
  const tTrust = TRUST_SCORES_I18N[locale] ?? TRUST_SCORES_I18N["en-US"]!;
  const { config, isLoading: configLoading } = useEvolutionConfig();
  const { mutate: updateConfig } = useUpdateEvolutionConfig();
  const { metrics, isLoading: metricsLoading } = useQualityMetrics();
  const { reports, isLoading: reportsLoading } = useHealthReports();
  const [tab, setTab] = useState("config");
  const registerSkill = useRegisterEvolutionSkill();
  const [mounted, setMounted] = useState(false);
  const [trustWindow, setTrustWindow] = useState(200);
  const trustQuery = useQuery({
    queryKey: ["skill-trust-scores", trustWindow],
    queryFn: async () => {
      try {
        return await getJSON<TrustScoresResponse>(
          `/api/skill-evolution/trust-scores?window=${trustWindow}`,
        );
      } catch {
        return { enabled: false, window: trustWindow, entries: [] } as TrustScoresResponse;
      }
    },
    enabled: tab === "trust",
  });

  useEffect(() => {
    setMounted(true);
  }, []);

  const healthySummary = useMemo(() => {
    if (!reports.length) return { healthy: 0, unhealthy: 0 };
    return {
      healthy: reports.filter((r) => r.healthy).length,
      unhealthy: reports.filter((r) => !r.healthy).length,
    };
  }, [reports]);

  const handleToggle = (key: string, value: boolean) => {
    if (!config) return;
    updateConfig({ ...config, [key]: value });
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto p-6">
      <header className="mb-6">
        <div className="flex items-center gap-2">
          <DnaIcon className="size-5 text-primary" />
          <h1 className="text-lg font-semibold text-foreground">
            {t.sidebar.evolution}
          </h1>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          {t.sidebar.evolutionDesc}
        </p>
      </header>

      {mounted && (
        <Tabs defaultValue="config" onValueChange={setTab} className="mb-4">
          <TabsList variant="line">
            <TabsTrigger value="config">{t.common.settings}</TabsTrigger>
            <TabsTrigger value="metrics">
              {t.sidebar.qualityMetrics}
            </TabsTrigger>
            <TabsTrigger value="health">{t.sidebar.healthCheck}</TabsTrigger>
            <TabsTrigger value="trust">{tTrust.tabLabel}</TabsTrigger>
          </TabsList>
        </Tabs>
      )}

      {/* Config tab */}
      {tab === "config" && (
        <div className="space-y-4">
          {configLoading ? (
            <p className="text-sm text-muted-foreground">{t.common.loading}</p>
          ) : config ? (
            <>
              <ToggleRow
                label={t.sidebar.evolutionEnabled}
                description={t.sidebar.evolutionEnabledDesc}
                checked={config.enabled}
                onChange={(v) => handleToggle("enabled", v)}
              />
              <ToggleRow
                label={t.sidebar.autoFix}
                description={t.sidebar.autoFixDesc}
                checked={config.auto_fix}
                onChange={(v) => handleToggle("auto_fix", v)}
              />
              <ToggleRow
                label={t.sidebar.autoDerive}
                description={t.sidebar.autoDeriveDesc}
                checked={config.auto_derive}
                onChange={(v) => handleToggle("auto_derive", v)}
              />
              <ToggleRow
                label={t.sidebar.autoCapture}
                description={t.sidebar.autoCaptureDesc}
                checked={config.auto_capture}
                onChange={(v) => handleToggle("auto_capture", v)}
              />
              <ToggleRow
                label={t.sidebar.qualityMonitoring}
                description={t.sidebar.qualityMonitoringDesc}
                checked={config.quality_monitoring}
                onChange={(v) => handleToggle("quality_monitoring", v)}
              />
              <ToggleRow
                label={t.sidebar.cloudSync}
                description={t.sidebar.cloudSyncDesc}
                checked={config.cloud_enabled}
                onChange={(v) => handleToggle("cloud_enabled", v)}
              />
              <div className="octo-panel rounded-[1.5rem] px-4 py-3">
                <p className="text-sm font-medium text-foreground">{t.sidebar.evolutionStartResearch}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {t.sidebar.evolutionStartResearchDesc}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {["deep-research", "github-deep-research"].map((skillName) => (
                    <button
                      key={skillName}
                      type="button"
                      className="inline-flex items-center rounded-md border px-3 py-1.5 text-xs hover:bg-muted"
                      onClick={() =>
                        registerSkill.mutate(skillName, {
                          onSuccess: () => toast.success(t.sidebar.evolutionStartSuccess),
                        })
                      }
                    >
                      {t.sidebar.evolutionStart} · {skillName}
                    </button>
                  ))}
                </div>
              </div>
            </>
          ) : null}
        </div>
      )}

      {/* Metrics tab */}
      {tab === "metrics" && (
        <div className="space-y-3">
          {metricsLoading ? (
            <p className="text-sm text-muted-foreground">{t.common.loading}</p>
          ) : metrics.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <ActivityIcon className="mb-3 size-10 opacity-30" />
              <p className="text-sm">{t.sidebar.noMetrics}</p>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {metrics.map((m) => (
                <div
                  key={m.skill_name}
                  className="octo-panel rounded-[1.5rem] p-4"
                >
                  <h3 className="text-sm font-medium">{m.skill_name}</h3>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
                    <Badge variant="secondary">
                      {t.sidebar.applied}: {m.applied_count}
                    </Badge>
                    <Badge variant="secondary">
                      {t.sidebar.success}: {m.success_count}
                    </Badge>
                    <Badge variant="secondary">
                      {t.sidebar.failures}: {m.failure_count}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Health tab */}
      {tab === "health" && (
        <div className="space-y-3">
          {reportsLoading ? (
            <p className="text-sm text-muted-foreground">{t.common.loading}</p>
          ) : reports.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <ZapIcon className="mb-3 size-10 opacity-30" />
              <p className="text-sm">{t.sidebar.noHealth}</p>
            </div>
          ) : (
            <>
              <div className="mb-4 flex gap-4">
                <Badge variant="outline" className="gap-1">
                  <CheckCircleIcon className="size-3 text-green-600" />
                  {t.sidebar.healthy}: {healthySummary.healthy}
                </Badge>
                <Badge variant="outline" className="gap-1">
                  <XCircleIcon className="size-3 text-red-500" />
                  {t.sidebar.unhealthy}: {healthySummary.unhealthy}
                </Badge>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {reports.map((r) => (
                  <div
                    key={r.skill_name}
                    className={`rounded-xl border p-4 shadow-sm ${
                      r.healthy
                        ? "border-green-200 bg-green-50/50 dark:border-green-900/30 dark:bg-green-950/20"
                        : "border-red-200 bg-red-50/50 dark:border-red-900/30 dark:bg-red-950/20"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      {r.healthy ? (
                        <CheckCircleIcon className="size-4 text-green-600" />
                      ) : (
                        <XCircleIcon className="size-4 text-red-500" />
                      )}
                      <h3 className="text-sm font-medium">{r.skill_name}</h3>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {t.sidebar.successRate}:{" "}
                      {(r.success_rate * 100).toFixed(0)}% · {t.sidebar.total}:{" "}
                      {r.total_executions}
                    </p>
                    {r.recommendation && r.recommendation !== "Healthy" && (
                      <p className="mt-1 text-xs text-red-600 dark:text-red-400">
                        {r.recommendation}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* Trust scores tab */}
      {tab === "trust" && (
        <div className="space-y-3" data-testid="trust-scores-panel">
          <div className="flex flex-wrap items-center gap-3">
            <Badge
              variant={trustQuery.data?.enabled ? "default" : "secondary"}
              data-testid="trust-scores-flag-badge"
            >
              {trustQuery.data?.enabled ? tTrust.observationOn : tTrust.observationOff}
            </Badge>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              {tTrust.windowLabel}
              <select
                className="rounded-md border px-2 py-1 text-xs"
                value={trustWindow}
                onChange={(e) => setTrustWindow(Number(e.target.value))}
              >
                {[50, 100, 200, 500, 1000].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {trustQuery.isLoading ? (
            <p className="text-sm text-muted-foreground">{t.common.loading}</p>
          ) : !trustQuery.data?.enabled ? (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <GaugeIcon className="mb-3 size-10 opacity-30" />
              <p className="text-sm">{tTrust.disabledHint}</p>
            </div>
          ) : (trustQuery.data?.entries ?? []).length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <GaugeIcon className="mb-3 size-10 opacity-30" />
              <p className="text-sm">{tTrust.emptyHint}</p>
            </div>
          ) : (
            <div className="overflow-hidden rounded-xl border">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-xs text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 text-left">{tTrust.tableSkill}</th>
                    <th className="px-3 py-2 text-right">{tTrust.tableTotal}</th>
                    <th className="px-3 py-2 text-right">{tTrust.tableSuccessRate}</th>
                    <th className="px-3 py-2 text-right">{tTrust.tableP95}</th>
                    <th className="px-3 py-2 text-right">{tTrust.tableTrust}</th>
                  </tr>
                </thead>
                <tbody>
                  {(trustQuery.data?.entries ?? []).map((e) => (
                    <tr
                      key={e.skill}
                      data-testid={`trust-scores-row-${e.skill}`}
                      className="border-t"
                    >
                      <td className="px-3 py-2 font-medium">{e.skill}</td>
                      <td className="px-3 py-2 text-right">{e.total}</td>
                      <td className="px-3 py-2 text-right">
                        {(e.success_rate * 100).toFixed(1)}%
                      </td>
                      <td className="px-3 py-2 text-right">
                        {Math.round(e.p95_latency_ms)}
                      </td>
                      <td className="px-3 py-2 text-right font-medium">
                        {e.trust_score.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-xs text-muted-foreground">{tTrust.footer}</p>
        </div>
      )}
    </div>
  );
}

function ToggleRow({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="octo-panel flex items-center justify-between rounded-[1.5rem] px-4 py-3">
      <div>
        <p className="text-sm font-medium text-foreground">{label}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
      <Switch checked={checked} onCheckedChange={onChange} />
    </div>
  );
}
