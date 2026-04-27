"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUpIcon, PencilIcon, PlusIcon, TrashIcon } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { getBackendBaseURL } from "@/core/config";
import { useI18n } from "@/core/i18n/hooks";
import { formatTimeAgo } from "@/core/utils/datetime";

import { SettingsSection } from "./settings-section";

// ---------- Types ----------

interface GlobalMemoryEntry {
  id: string;
  title: string;
  content: string;
  source: string;
  createdAt: string;
  updatedAt: string;
}

interface GlobalMemoryStore {
  entries: GlobalMemoryEntry[];
}

// ---------- API helpers ----------

const baseUrl = () => `${getBackendBaseURL()}/api/memory/global`;

async function fetchGlobalMemory(): Promise<GlobalMemoryStore> {
  const res = await fetch(baseUrl());
  if (!res.ok) throw new Error("Failed to fetch global memory");
  return res.json() as Promise<GlobalMemoryStore>;
}

async function createEntry(body: { title: string; content: string }): Promise<GlobalMemoryEntry> {
  const res = await fetch(baseUrl(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("Failed to create entry");
  return res.json() as Promise<GlobalMemoryEntry>;
}

async function updateEntry(id: string, body: { title: string; content: string }): Promise<GlobalMemoryEntry> {
  const res = await fetch(`${baseUrl()}/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("Failed to update entry");
  return res.json() as Promise<GlobalMemoryEntry>;
}

async function deleteEntry(id: string): Promise<void> {
  const res = await fetch(`${baseUrl()}/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete entry");
}

async function importFile(file: File): Promise<GlobalMemoryEntry> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${baseUrl()}/import`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail ?? "Import failed");
  }
  return res.json() as Promise<GlobalMemoryEntry>;
}

// ---------- Component ----------

export function GlobalMemorySettings() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["global-memory"],
    queryFn: fetchGlobalMemory,
  });

  const entries = data?.entries ?? [];

  // Edit state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editContent, setEditContent] = useState("");
  const [isNew, setIsNew] = useState(false);

  const invalidate = useCallback(
    () => queryClient.invalidateQueries({ queryKey: ["global-memory"] }),
    [queryClient],
  );

  const createMutation = useMutation({
    mutationFn: (body: { title: string; content: string }) => createEntry(body),
    onSuccess: async () => {
      await invalidate();
      resetForm();
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { title: string; content: string } }) =>
      updateEntry(id, body),
    onSuccess: async () => {
      await invalidate();
      resetForm();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteEntry(id),
    onSuccess: async () => {
      await invalidate();
    },
  });

  const importMutation = useMutation({
    mutationFn: (file: File) => importFile(file),
    onSuccess: async () => {
      await invalidate();
      toast.success(t.settings.globalMemory.importSuccess);
    },
    onError: (err: Error) => {
      toast.error(err.message);
    },
  });

  function resetForm() {
    setEditingId(null);
    setEditTitle("");
    setEditContent("");
    setIsNew(false);
  }

  function startNew() {
    setIsNew(true);
    setEditingId(null);
    setEditTitle("");
    setEditContent("");
  }

  function startEdit(entry: GlobalMemoryEntry) {
    setIsNew(false);
    setEditingId(entry.id);
    setEditTitle(entry.title);
    setEditContent(entry.content);
  }

  function handleSave() {
    if (isNew) {
      createMutation.mutate({ title: editTitle, content: editContent });
    } else if (editingId) {
      updateMutation.mutate({ id: editingId, body: { title: editTitle, content: editContent } });
    }
  }

  function handleDelete(id: string) {
    if (window.confirm(t.settings.globalMemory.deleteConfirm)) {
      deleteMutation.mutate(id);
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) {
      importMutation.mutate(file);
    }
    // Reset input so the same file can be re-selected
    e.target.value = "";
  }

  const isSaving = createMutation.isPending || updateMutation.isPending;
  const showForm = isNew || editingId !== null;

  return (
    <SettingsSection
      title={t.settings.globalMemory.title}
      description={t.settings.globalMemory.description}
    >
      {/* Toolbar */}
      <div className="flex gap-2 flex-wrap">
        <Button
          variant="outline"
          size="sm"
          onClick={startNew}
          disabled={showForm}
        >
          <PlusIcon className="mr-1.5 size-4" />
          {t.settings.globalMemory.addEntry}
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => fileInputRef.current?.click()}
          disabled={importMutation.isPending}
        >
          <FileUpIcon className="mr-1.5 size-4" />
          {t.settings.globalMemory.importFile}
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".txt,.md,.json,.doc,.docx"
          className="hidden"
          onChange={handleFileChange}
          aria-label={t.settings.globalMemory.importFile}
        />
      </div>

      {/* Inline editor */}
      {showForm && (
        <Card variant="compact" className="mt-4">
          <CardContent className="space-y-3 pt-4">
            <Input
              placeholder={t.settings.globalMemory.titlePlaceholder}
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              aria-label={t.settings.globalMemory.titlePlaceholder}
            />
            <Textarea
              placeholder={t.settings.globalMemory.contentPlaceholder}
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              rows={8}
              className="font-mono text-sm"
              aria-label={t.settings.globalMemory.contentPlaceholder}
            />
            <div className="flex gap-2 justify-end">
              <Button variant="ghost" size="sm" onClick={resetForm}>
                {t.settings.globalMemory.cancel}
              </Button>
              <Button
                size="sm"
                onClick={handleSave}
                disabled={isSaving || (!editTitle.trim() && !editContent.trim())}
              >
                {t.settings.globalMemory.save}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Entries list */}
      {isLoading ? (
        <div className="text-muted-foreground text-sm mt-4">{t.common.loading}</div>
      ) : entries.length === 0 && !showForm ? (
        <div className="text-muted-foreground text-sm mt-4">
          {t.settings.globalMemory.empty}
        </div>
      ) : (
        <div className="mt-4 space-y-3">
          {entries.map((entry) => (
            <Card key={entry.id} variant="compact">
              <CardContent className="pt-3 pb-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <h4 className="font-medium text-sm truncate">{entry.title || "(untitled)"}</h4>
                    <p className="text-muted-foreground text-xs mt-0.5 line-clamp-2 whitespace-pre-wrap">
                      {entry.content.slice(0, 200)}
                      {entry.content.length > 200 ? "…" : ""}
                    </p>
                    <div className="text-muted-foreground/60 text-[11px] mt-1.5 flex gap-3">
                      {entry.source !== "manual" && (
                        <span>{t.settings.globalMemory.source}: {entry.source}</span>
                      )}
                      {entry.updatedAt && (
                        <span>{t.settings.globalMemory.updatedAt}: {formatTimeAgo(entry.updatedAt)}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-7"
                      onClick={() => startEdit(entry)}
                      aria-label={t.settings.globalMemory.editEntry}
                    >
                      <PencilIcon className="size-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-7 text-destructive hover:text-destructive"
                      onClick={() => handleDelete(entry.id)}
                      aria-label={t.settings.globalMemory.deleteEntry}
                    >
                      <TrashIcon className="size-3.5" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </SettingsSection>
  );
}
