"use client";

import {
  CheckCircleIcon,
  Edit3Icon,
  PlusIcon,
  SaveIcon,
  SearchIcon,
  SparklesIcon,
  Trash2Icon,
  XCircleIcon,
} from "lucide-react";
import { useMemo, useState, useEffect } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/core/i18n/hooks";
import {
  useCreateSkill,
  useDeleteSkill,
  useEnableSkill,
  useSkills,
  useUpdateSkill,
} from "@/core/skills/hooks";
import { env } from "@/env";

interface SkillFormState {
  name: string;
  description: string;
  license: string;
  content: string;
}

const EMPTY_FORM: SkillFormState = {
  name: "",
  description: "",
  license: "",
  content: "",
};

export default function SkillsConfigPage() {
  const { t } = useI18n();
  const { skills, isLoading } = useSkills();
  const { mutate: enableSkill } = useEnableSkill();
  const deleteSkill = useDeleteSkill();
  const createSkill = useCreateSkill();
  const updateSkill = useUpdateSkill();
  const [filter, setFilter] = useState<string>("public");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [enabledFilter, setEnabledFilter] = useState<"all" | "enabled" | "disabled">("all");
  const [mounted, setMounted] = useState(false);
  const [form, setForm] = useState<SkillFormState>(EMPTY_FORM);
  const [editingSkill, setEditingSkill] = useState<string | null>(null);
  const [isEditorOpen, setIsEditorOpen] = useState(false);

  useEffect(() => { setMounted(true); }, []);

  const filteredSkills = useMemo(() => {
    const normalized = searchQuery.trim().toLowerCase();
    return (skills ?? [])
      .filter((skill) => skill.category === filter)
      .filter((skill) => {
        if (enabledFilter === "enabled") return skill.enabled === true;
        if (enabledFilter === "disabled") return skill.enabled === false;
        return true;
      })
      .filter((skill) => {
        if (!normalized) return true;
        const haystack = `${skill.name} ${skill.description ?? ""} ${skill.license ?? ""}`.toLowerCase();
        return haystack.includes(normalized);
      });
  }, [skills, filter, enabledFilter, searchQuery]);

  function updateField<K extends keyof SkillFormState>(key: K, value: SkillFormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function startEdit(skillName: string) {
    const skill = skills.find((s) => s.name === skillName);
    if (!skill) return;
    setEditingSkill(skillName);
    setForm({ name: skill.name, description: skill.description, license: skill.license ?? "", content: "" });
    setIsEditorOpen(true);
  }

  function startCreate() {
    setEditingSkill(null);
    setForm(EMPTY_FORM);
    setIsEditorOpen(true);
  }

  function resetForm() {
    setEditingSkill(null);
    setForm(EMPTY_FORM);
    setIsEditorOpen(false);
  }

  async function handleSave() {
    if (!form.name.trim() || !form.description.trim()) {
      toast.error("Name and description are required.");
      return;
    }
    try {
      if (editingSkill) {
        await updateSkill.mutateAsync({
          skillName: editingSkill,
          request: {
            description: form.description.trim(),
            license: form.license,
            content: form.content.trim() || undefined,
          },
        });
        toast.success("Skill updated.");
      } else {
        await createSkill.mutateAsync({
          name: form.name.trim(),
          description: form.description.trim(),
          license: form.license.trim() || undefined,
          content: form.content.trim() || undefined,
        });
        toast.success("Skill created.");
      }
      resetForm();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to save skill.");
    }
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto p-6">
      <header className="mb-6 flex items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-foreground">{t.settings.skills.title}</h1>
          <p className="text-sm text-muted-foreground">{t.settings.skills.description}</p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" onClick={startCreate}>
            <PlusIcon className="size-4" />
            Add skill
          </Button>
        </div>
      </header>

      {isEditorOpen ? (
      <div className="octo-panel mb-6 rounded-[1.5rem] p-5">
        <div className="mb-3">
          <div className="text-sm font-medium text-foreground">
            {editingSkill ? `Edit: ${editingSkill}` : "Create skill"}
          </div>
          <p className="text-xs text-muted-foreground">
            Define a custom skill with name, description and optional content.
          </p>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground">Name (hyphen-case)</span>
            <Input value={form.name} disabled={!!editingSkill} onChange={(e) => updateField("name", e.target.value)} placeholder="my-custom-skill" />
          </label>
          <label className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground">License</span>
            <Input value={form.license} onChange={(e) => updateField("license", e.target.value)} placeholder="MIT" />
          </label>
          <label className="space-y-1 md:col-span-2">
            <span className="text-xs font-medium text-muted-foreground">Description</span>
            <Textarea value={form.description} onChange={(e) => updateField("description", e.target.value)} placeholder="What does this skill do?" rows={2} />
          </label>
          <label className="space-y-1 md:col-span-2">
            <span className="text-xs font-medium text-muted-foreground">SKILL.md body (optional)</span>
            <Textarea value={form.content} onChange={(e) => updateField("content", e.target.value)} placeholder="Additional instructions..." rows={3} className="font-mono text-xs" />
          </label>
        </div>
        <div className="mt-4 flex gap-2">
          <Button
            size="sm"
            onClick={() => void handleSave()}
            disabled={createSkill.isPending || updateSkill.isPending}
          >
            <SaveIcon className="size-4" />{editingSkill ? "Save changes" : "Create skill"}
          </Button>
          <Button size="sm" variant="outline" onClick={resetForm}>Close</Button>
        </div>
      </div>
      ) : null}

      {!mounted ? <div className="mb-4 h-9" /> : (
        <Tabs defaultValue="public" onValueChange={setFilter} className="mb-4">
          <TabsList variant="line">
            <TabsTrigger value="public">{t.common.public}</TabsTrigger>
            <TabsTrigger value="custom">{t.common.custom}</TabsTrigger>
          </TabsList>
        </Tabs>
      )}

      {mounted ? (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <div className="relative min-w-0 flex-1">
            <SearchIcon
              aria-hidden="true"
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              aria-label="Filter skills by name, description, or license"
              className="pl-9"
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Filter skills by name, description, or license…"
              type="search"
              value={searchQuery}
            />
          </div>
          <div
            aria-label="Filter by enabled state"
            className="flex items-center gap-1 rounded-full border border-border/60 bg-background/60 p-1 text-xs"
            role="group"
          >
            {(["all", "enabled", "disabled"] as const).map((option) => (
              <button
                className={
                  enabledFilter === option
                    ? "rounded-full bg-primary px-3 py-1 font-medium text-primary-foreground"
                    : "rounded-full px-3 py-1 text-muted-foreground hover:text-foreground"
                }
                key={option}
                onClick={() => setEnabledFilter(option)}
                type="button"
              >
                {option === "all" ? "All" : option === "enabled" ? "Enabled" : "Disabled"}
              </button>
            ))}
          </div>
          <span className="text-xs text-muted-foreground" aria-live="polite">
            {filteredSkills.length} / {(skills ?? []).filter((s) => s.category === filter).length}
          </span>
        </div>
      ) : null}

      {isLoading ? (
        <div className="text-sm text-muted-foreground">{t.common.loading}</div>
      ) : filteredSkills.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <SparklesIcon className="mb-3 size-10 opacity-30" />
          <p className="text-sm">No skills in this category yet.</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filteredSkills.map((skill) => (
            <div key={skill.name} className="octo-panel flex flex-col justify-between rounded-[1.5rem] p-4 transition-shadow hover:translate-y-[-1px] hover:shadow-[3px_3px_7px_var(--neu-dark-strong),_-3px_-3px_7px_var(--neu-light-strong)]">
              <div className="mb-3">
                <div className="flex items-start justify-between gap-2">
                  <h3 className="min-w-0 break-words text-sm font-medium text-foreground">{skill.name}</h3>
                  <div className="flex gap-1">
                    {skill.category === "custom" && (
                      <>
                        <Button
                          aria-label={`Edit ${skill.name}`}
                          size="icon"
                          variant="ghost"
                          className="size-7"
                          title="Edit"
                          onClick={() => startEdit(skill.name)}
                        >
                          <Edit3Icon className="size-3.5 text-muted-foreground hover:text-primary" />
                        </Button>
                        <Button
                          aria-label={`Delete ${skill.name}`}
                          size="icon"
                          variant="ghost"
                          className="size-7"
                          title="Delete"
                          onClick={() => {
                            if (window.confirm(`Delete skill "${skill.name}"?`)) {
                              deleteSkill.mutate({ skillName: skill.name }, {
                                onSuccess: () => {
                                  toast.success("Skill deleted.");
                                  if (editingSkill === skill.name) {
                                    resetForm();
                                  }
                                },
                                onError: (err) => toast.error(err instanceof Error ? err.message : "Failed"),
                              });
                            }
                          }}
                        >
                          <Trash2Icon className="size-3.5 text-muted-foreground hover:text-destructive" />
                        </Button>
                      </>
                    )}
                  </div>
                </div>
                <p className="mt-1 break-words line-clamp-3 text-xs text-muted-foreground">{skill.description}</p>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex flex-wrap gap-1.5">
                  <Badge variant="outline" className={skill.enabled ? "gap-1 border-green-500/30 text-[10px] text-green-600" : "gap-1 border-muted text-[10px] text-muted-foreground"}>
                    {skill.enabled ? (<><CheckCircleIcon className="size-3" /> Active</>) : (<><XCircleIcon className="size-3" /> Disabled</>)}
                  </Badge>
                  {skill.license && <Badge variant="secondary" className="text-[10px]">{skill.license}</Badge>}
                </div>
                <Switch
                  aria-label={`Enable ${skill.name}`}
                  checked={skill.enabled}
                  disabled={env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true"}
                  onCheckedChange={(checked) => enableSkill({ skillName: skill.name, enabled: checked })}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
