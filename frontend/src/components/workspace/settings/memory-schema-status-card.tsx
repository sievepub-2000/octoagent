"use client";

import { useQuery } from "@tanstack/react-query";
import { DatabaseIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { getJSON } from "@/core/api/http";
import { useI18n } from "@/core/i18n/hooks";

type MemorySchemaStatus = {
  storage_path: string;
  schema_version: string;
  v2_available: boolean;
  legacy_backup_present: boolean;
  prefer_v2: boolean;
  note: string;
};

type Locale = "en-US" | "zh-CN" | "zh-TW" | "ja" | "ko";

type Copy = {
  title: string;
  description: string;
  schemaVersion: string;
  storagePath: string;
  v2Available: string;
  legacyBackup: string;
  preferV2: string;
  on: string;
  off: string;
  present: string;
  missing: string;
  loading: string;
  error: string;
};

const I18N: Record<Locale, Copy> = {
  "en-US": {
    title: "Memory schema status",
    description: "Observation-only view of the memory store shape.",
    schemaVersion: "Schema version",
    storagePath: "Storage path",
    v2Available: "memory.v2.json",
    legacyBackup: "Legacy backup",
    preferV2: "MEMORY_PREFER_V2",
    on: "on",
    off: "off",
    present: "present",
    missing: "missing",
    loading: "Loading…",
    error: "Schema status unavailable",
  },
  "zh-CN": {
    title: "Memory 架构状态",
    description: "只读的记忆存储结构观察视图。",
    schemaVersion: "架构版本",
    storagePath: "存储路径",
    v2Available: "memory.v2.json",
    legacyBackup: "旧版备份",
    preferV2: "MEMORY_PREFER_V2",
    on: "开",
    off: "关",
    present: "已生成",
    missing: "未生成",
    loading: "加载中…",
    error: "架构状态不可用",
  },
  "zh-TW": {
    title: "Memory 架構狀態",
    description: "唯讀的記憶儲存結構觀察視圖。",
    schemaVersion: "架構版本",
    storagePath: "儲存路徑",
    v2Available: "memory.v2.json",
    legacyBackup: "舊版備份",
    preferV2: "MEMORY_PREFER_V2",
    on: "開",
    off: "關",
    present: "已生成",
    missing: "未生成",
    loading: "載入中…",
    error: "架構狀態不可用",
  },
  ja: {
    title: "Memory スキーマ状態",
    description: "メモリーストア構造の観察専用ビュー。",
    schemaVersion: "スキーマ版",
    storagePath: "保存パス",
    v2Available: "memory.v2.json",
    legacyBackup: "旧バックアップ",
    preferV2: "MEMORY_PREFER_V2",
    on: "有効",
    off: "無効",
    present: "生成済み",
    missing: "未生成",
    loading: "読込中…",
    error: "スキーマ状態を取得できません",
  },
  ko: {
    title: "Memory 스키마 상태",
    description: "메모리 저장소 구조의 관찰 전용 뷰.",
    schemaVersion: "스키마 버전",
    storagePath: "저장 경로",
    v2Available: "memory.v2.json",
    legacyBackup: "레거시 백업",
    preferV2: "MEMORY_PREFER_V2",
    on: "켬",
    off: "끔",
    present: "생성됨",
    missing: "없음",
    loading: "로딩 중…",
    error: "스키마 상태를 가져올 수 없음",
  },
};

function pickCopy(locale: string): Copy {
  const key = locale as Locale;
  return I18N[key] ?? I18N["en-US"];
}

export function MemorySchemaStatusCard() {
  const { locale } = useI18n();
  const copy = pickCopy(locale);
  const { data, isLoading, isError } = useQuery<MemorySchemaStatus>({
    queryKey: ["memory", "schema-status"],
    queryFn: () => getJSON<MemorySchemaStatus>("/api/memory/schema-status"),
    refetchOnWindowFocus: false,
    retry: false,
  });

  return (
    <section
      data-testid="memory-schema-status"
      aria-label="Memory schema observation card"
      className="octo-panel mb-5 rounded-[1rem] p-4 text-sm"
    >
      <header className="mb-3 flex items-center gap-2">
        <DatabaseIcon aria-hidden="true" className="size-4 text-primary" />
        <h2 className="text-sm font-semibold text-foreground">{copy.title}</h2>
      </header>
      <p className="mb-3 text-xs text-muted-foreground">{copy.description}</p>

      {isLoading ? (
        <p className="text-xs text-muted-foreground">{copy.loading}</p>
      ) : isError || !data ? (
        <p className="text-xs text-destructive">{copy.error}</p>
      ) : (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <Badge variant="outline" className="text-[10px]">
              {copy.schemaVersion}: {data.schema_version}
            </Badge>
            <Badge
              variant={data.v2_available ? "default" : "secondary"}
              className="text-[10px]"
              data-testid="memory-schema-v2-available"
            >
              {copy.v2Available}: {data.v2_available ? copy.present : copy.missing}
            </Badge>
            <Badge
              variant={data.legacy_backup_present ? "default" : "secondary"}
              className="text-[10px]"
              data-testid="memory-schema-legacy-backup"
            >
              {copy.legacyBackup}: {data.legacy_backup_present ? copy.present : copy.missing}
            </Badge>
            <Badge
              variant={data.prefer_v2 ? "default" : "outline"}
              className="text-[10px]"
              data-testid="memory-schema-prefer-v2"
            >
              {copy.preferV2}: {data.prefer_v2 ? copy.on : copy.off}
            </Badge>
          </div>
          <div className="text-[11px] text-muted-foreground">
            <span className="font-medium">{copy.storagePath}: </span>
            <span className="font-mono break-all">{data.storage_path}</span>
          </div>
        </div>
      )}
    </section>
  );
}
