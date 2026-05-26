"use client";

import { DatabaseIcon, DownloadIcon, SparklesIcon } from "lucide-react";
import { useEffect, useState } from "react";
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

const EMBEDDING_MODELS = [
  { value: "sentence-transformers/all-MiniLM-L6-v2", label: "MiniLM-L6 (英文, 384d, 88MB)" },
  { value: "BAAI/bge-small-zh-v1.5", label: "BGE-small-zh (中文, 512d, 184MB)" },
  { value: "BAAI/bge-m3", label: "BGE-M3 (多语言, 1024d, 2.3GB)" },
];

const RERANKER_MODELS = [
  { value: "BAAI/bge-reranker-base", label: "BGE-Reranker Base (278MB)" },
  { value: "BAAI/bge-reranker-v2-m3", label: "BGE-Reranker v2 M3 (568MB)" },
];

export function RagSettingsPage() {
  const { data, isLoading, error, refetch } = useRagConfig();
  const update = useUpdateRagConfig();
  const download = useDownloadModel();
  const [form, setForm] = useState<RagConfig | null>(null);

  useEffect(() => {
    if (data?.config) setForm(data.config);
  }, [data]);

  if (isLoading) {
    return (
      <SettingsSection title="RAG 检索" description="嵌入与重排模型配置">
        <Skeleton className="h-48 w-full rounded-xl" />
      </SettingsSection>
    );
  }

  if (error || !data || !form) {
    return (
      <SettingsSection title="RAG 检索" description="嵌入与重排模型配置">
        <Card variant="status">
          <CardContent className="p-6 text-sm text-destructive">
            加载配置失败：{error instanceof Error ? error.message : "未知错误"}
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
      toast.success("RAG 配置已保存");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleDownload(kind: "embedding" | "reranker", model: string) {
    try {
      toast.info(`开始下载 ${model}（可能需要几分钟）...`);
      await download.mutateAsync({ model, kind });
      toast.success(`${model} 下载完成`);
      await refetch();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <SettingsSection
      title="RAG 检索"
      description="配置嵌入模型与重排模型；模型从 Hugging Face 下载到 ~/.cache/huggingface/hub/。"
    >
      <div className="space-y-4">
        {/* Embedding */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <DatabaseIcon className="size-4" />
              嵌入模型 (Embedding)
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-2">
              <label className="text-sm font-medium">模型</label>
              <Select
                value={form.embedding_model}
                onValueChange={(v) => setForm({ ...form, embedding_model: v })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {EMBEDDING_MODELS.map((m) => (
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
                  {data.embedding_status.cached ? "已缓存" : "未下载"}
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
                {data.embedding_status.cached ? "重新下载" : "下载"}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Reranker */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <SparklesIcon className="size-4" />
              重排模型 (Cross-Encoder Reranker)
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <label className="text-sm font-medium">启用二段重排</label>
                <p className="text-xs text-muted-foreground">
                  在 hybrid 检索结果上用 Cross-Encoder 重排前 top_k 个候选。
                </p>
              </div>
              <Switch
                checked={form.reranker_enabled}
                onCheckedChange={(v) => setForm({ ...form, reranker_enabled: v })}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">重排模型</label>
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
                  {data.reranker_status.cached ? "已缓存" : "未下载"}
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
                {data.reranker_status.cached ? "重新下载" : "下载"}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Generic */}
        <Card>
          <CardHeader>
            <CardTitle>检索参数</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-2">
              <label className="text-sm font-medium">默认 top_k</label>
              <Input
                type="number"
                min={1}
                max={100}
                value={form.top_k_default}
                onChange={(e) => setForm({ ...form, top_k_default: Number(e.target.value) || 10 })}
              />
            </div>
            <p className="text-xs text-muted-foreground">
              配置文件位置：<code>{data.config_file}</code>
            </p>
          </CardContent>
        </Card>

        <div className="flex justify-end gap-2">
          <Button
            variant="ghost"
            disabled={!dirty || update.isPending}
            onClick={() => setForm(data.config)}
          >
            重置
          </Button>
          <Button onClick={handleSave} disabled={!dirty || update.isPending}>
            {update.isPending ? "保存中…" : "保存"}
          </Button>
        </div>
      </div>
    </SettingsSection>
  );
}
