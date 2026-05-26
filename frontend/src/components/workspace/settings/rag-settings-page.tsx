"use client";

import { DatabaseIcon, DownloadIcon, SparklesIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { useI18n } from "@/core/i18n/hooks";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  formatBytes,
  useDownloadModel,
  useRagConfig,
  useUpdateRagConfig,
  type RagConfig,
} from "@/core/rag-config";

import { SettingsSection } from "./settings-section";

function getEmbeddingModels(t: ReturnType<typeof useI18n>["t"]) {
  return [
    { value: "sentence-transformers/all-MiniLM-L6-v2", label: t.ragSettings.modelLabelMiniLM },
    { value: "BAAI/bge-small-zh-v1.5", label: t.ragSettings.modelLabelBgeSmallZh },
    { value: "BAAI/bge-m3", label: t.ragSettings.modelLabelBgeM3 },
  ];
}

const RERANKER_MODELS = [
  { value: "BAAI/bge-reranker-base", label: "BGE-Reranker Base (278MB)" },
  { value: "BAAI/bge-reranker-v2-m3", label: "BGE-Reranker v2 M3 (568MB)" },
];

export function RagSettingsPage() {
  const { t } = useI18n();
  const embeddingModels = getEmbeddingModels(t);

  const { data, isLoading, error, refetch } = useRagConfig();
  const update = useUpdateRagConfig();
  const download = useDownloadModel();
  const [form, setForm] = useState<RagConfig | null>(null);

  useEffect(() => {
    if (data?.config) setForm(data.config);
  }, [data]);

  if (isLoading) {
    return (
      <SettingsSection title={t.ragSettings.sectionTitle} description={t.ragSettings.sectionDescription}>
        <Skeleton className="h-48 w-full rounded-xl" />
      </SettingsSection>
    );
  }

  if (error || !data || !form) {
    return (
      <SettingsSection title={t.ragSettings.sectionTitle} description={t.ragSettings.sectionDescription}>
        <Card variant="status">
          <CardContent className="p-6 text-sm text-destructive">
            {t.ragSettings.loadFailed}{error instanceof Error ? error.message : t.ragSettings.unknownError}
          </CardContent>
        </Card>
      </SettingsSection>
    );
  }

  const dirty =
    form.embedding_model !== data.config.embedding_model ||
    form.reranker_enabled !== data.config.reranker_enabled ||
    form.reranker_model !== data.config.reranker_model ||
    form.top_k_default !== data.config.top_k_default;

  async function handleSave() {
    if (!form) return;
    try {
      await update.mutateAsync(form);
      toast.success(t.ragSettings.savedToast);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleDownload(kind: "embedding" | "reranker", model: string) {
    try {
      toast.info(t.ragSettings.downloadStart.replace("{model}", model));
      await download.mutateAsync({ model, kind });
      toast.success(t.ragSettings.downloadDone.replace("{model}", model));
      await refetch();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <SettingsSection
      title={t.ragSettings.sectionTitle}
      description={t.ragSettings.sectionFullDescription}
    >
      <div className="space-y-4">
        {/* Embedding */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <DatabaseIcon className="size-4" />
              {t.ragSettings.embeddingTitle}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-2">
              <label className="text-sm font-medium">{t.ragSettings.rerankerEnable}</label>
              <Select
                value={form.embedding_model}
                onValueChange={(v) => setForm({ ...form, embedding_model: v })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {embeddingModels.map((m) => (
                    <SelectItem key={m.value} value={m.value}>
                      {m.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center justify-between rounded-md border bg-muted/30 p-3 text-sm">
              <div className="flex items-center gap-2">
                <Badge variant={data.embedding_status.cached ? "secondary" : "outline"}>
                  {data.embedding_status.cached ? t.ragSettings.cached : t.ragSettings.notDownloaded}
                </Badge>
                {data.embedding_status.cached && (
                  <span className="text-muted-foreground">
                    {formatBytes(data.embedding_status.size_bytes)}
                  </span>
                )}
              </div>
              <Button
                size="sm"
                variant="outline"
                disabled={download.isPending}
                onClick={() => handleDownload("embedding", form.embedding_model)}
              >
                <DownloadIcon className="mr-1 size-3" />
                {data.embedding_status.cached ? t.ragSettings.redownload : t.ragSettings.download}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Reranker */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <SparklesIcon className="size-4" />
              {t.ragSettings.rerankerTitle}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <label className="text-sm font-medium">{t.ragSettings.rerankerEnable}</label>
                <p className="text-xs text-muted-foreground">
                  {t.ragSettings.rerankerHint}
                </p>
              </div>
              <Switch
                checked={form.reranker_enabled}
                onCheckedChange={(v) => setForm({ ...form, reranker_enabled: v })}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">{t.ragSettings.rerankerModel}</label>
              <Select
                value={form.reranker_model}
                onValueChange={(v) => setForm({ ...form, reranker_model: v })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {RERANKER_MODELS.map((m) => (
                    <SelectItem key={m.value} value={m.value}>
                      {m.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center justify-between rounded-md border bg-muted/30 p-3 text-sm">
              <div className="flex items-center gap-2">
                <Badge variant={data.reranker_status.cached ? "secondary" : "outline"}>
                  {data.reranker_status.cached ? t.ragSettings.cached : t.ragSettings.notDownloaded}
                </Badge>
                {data.reranker_status.cached && (
                  <span className="text-muted-foreground">
                    {formatBytes(data.reranker_status.size_bytes)}
                  </span>
                )}
              </div>
              <Button
                size="sm"
                variant="outline"
                disabled={download.isPending}
                onClick={() => handleDownload("reranker", form.reranker_model)}
              >
                <DownloadIcon className="mr-1 size-3" />
                {data.reranker_status.cached ? t.ragSettings.redownload : t.ragSettings.download}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Generic */}
        <Card>
          <CardHeader>
            <CardTitle>{t.ragSettings.paramsTitle}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-2">
              <label className="text-sm font-medium">{t.ragSettings.defaultTopK}</label>
              <Input
                type="number"
                min={1}
                max={100}
                value={form.top_k_default}
                onChange={(e) => setForm({ ...form, top_k_default: Number(e.target.value) || 10 })}
              />
            </div>
            <p className="text-xs text-muted-foreground">
              {t.ragSettings.configLocation}<code>{data.config_file}</code>
            </p>
          </CardContent>
        </Card>

        <div className="flex justify-end gap-2">
          <Button
            variant="ghost"
            disabled={!dirty || update.isPending}
            onClick={() => setForm(data.config)}
          >{t.ragSettings.reset}</Button>
          <Button onClick={handleSave} disabled={!dirty || update.isPending}>
            {update.isPending ? t.ragSettings.saving : t.ragSettings.save}
          </Button>
        </div>
      </div>
    </SettingsSection>
  );
}
