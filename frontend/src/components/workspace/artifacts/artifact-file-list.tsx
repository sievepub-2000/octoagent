import { DownloadIcon, LoaderIcon, PackageIcon, Trash2Icon } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { deleteArtifact, urlOfArtifact } from "@/core/artifacts/utils";
import { useI18n } from "@/core/i18n/hooks";
import { installSkill } from "@/core/skills/api";
import {
  getFileExtensionDisplayName,
  getFileIcon,
  getFileName,
} from "@/core/utils/files";
import { cn } from "@/lib/utils";

import { useArtifacts } from "./context";

export function ArtifactFileList({
  className,
  downloadOnly = false,
  files,
  threadId,
}: {
  className?: string;
  downloadOnly?: boolean;
  files: string[];
  threadId: string;
}) {
  const { t } = useI18n();
  const {
    artifacts,
    setArtifacts,
    select: selectArtifact,
    selectedArtifact,
    deselect,
    setOpen,
  } = useArtifacts();
  const [installingFile, setInstallingFile] = useState<string | null>(null);
  const [deletingFile, setDeletingFile] = useState<string | null>(null);
  const [displayFiles, setDisplayFiles] = useState<string[]>(files);

  // Sync when the parent re-feeds a fresh list (e.g. after server re-fetch)
  useEffect(() => {
    setDisplayFiles(files);
  }, [files]);

  const handleClick = useCallback(
    (filepath: string) => {
      if (downloadOnly) return;
      selectArtifact(filepath);
      setOpen(true);
    },
    [downloadOnly, selectArtifact, setOpen],
  );

  const handleInstallSkill = useCallback(
    async (e: React.MouseEvent, filepath: string) => {
      e.stopPropagation();
      e.preventDefault();

      if (installingFile) return;

      setInstallingFile(filepath);
      try {
        const result = await installSkill({
          thread_id: threadId,
          path: filepath,
        });
        if (result.success) {
          toast.success(result.message);
        } else {
          toast.error(result.message || "Failed to install skill");
        }
      } catch (error) {
        console.error("Failed to install skill:", error);
        toast.error("Failed to install skill");
      } finally {
        setInstallingFile(null);
      }
    },
    [threadId, installingFile],
  );

  const handleDelete = useCallback(
    async (e: React.MouseEvent, filepath: string) => {
      e.stopPropagation();
      e.preventDefault();
      if (deletingFile) return;
      if (!window.confirm(t.common.deleteConfirm)) return;

      setDeletingFile(filepath);
      try {
        await deleteArtifact({ threadId, filepath });
        setArtifacts(artifacts.filter((f) => f !== filepath));
        setDisplayFiles((prev) => prev.filter((f) => f !== filepath));
        if (selectedArtifact === filepath) {
          deselect();
        }
        toast.success(`${t.common.delete}: ${getFileName(filepath)}`);
      } catch (error) {
        console.error("Failed to delete artifact:", error);
        toast.error(
          error instanceof Error ? error.message : "Failed to delete artifact",
        );
      } finally {
        setDeletingFile(null);
      }
    },
    [
      artifacts,
      deletingFile,
      deselect,
      selectedArtifact,
      setArtifacts,
      t.common.delete,
      t.common.deleteConfirm,
      threadId,
    ],
  );

  return (
    <ul className={cn("flex w-full flex-col gap-4", className)}>
      {displayFiles.map((file) => (
        <Card
          key={file}
          className={cn("relative p-3", !downloadOnly && "cursor-pointer")}
          onClick={() => handleClick(file)}
        >
          <div className="flex items-center gap-2">
            {/* Left-side action cluster: download + delete. Stays visible no matter how long the filename is. */}
            <div className="flex shrink-0 items-center gap-1">
              <a
                href={urlOfArtifact({
                  filepath: file,
                  threadId: threadId,
                  download: true,
                })}
                target="_blank"
                onClick={(e) => e.stopPropagation()}
                aria-label={t.common.download}
                title={t.common.download}
              >
                <Button variant="ghost" size="icon" type="button">
                  <DownloadIcon className="size-4" />
                </Button>
              </a>
              <Button
                variant="ghost"
                size="icon"
                type="button"
                disabled={deletingFile === file}
                onClick={(e) => handleDelete(e, file)}
                aria-label={t.common.delete}
                title={t.common.delete}
              >
                {deletingFile === file ? (
                  <LoaderIcon className="size-4 animate-spin" />
                ) : (
                  <Trash2Icon className="size-4 text-destructive" />
                )}
              </Button>
            </div>

            {/* File icon */}
            <div className="shrink-0">{getFileIcon(file, "size-6")}</div>

            {/* Filename + extension label — truncates instead of pushing buttons off-screen. */}
            <div className="flex min-w-0 flex-1 flex-col">
              <CardTitle className="truncate text-sm" title={getFileName(file)}>
                {getFileName(file)}
              </CardTitle>
              <CardDescription className="truncate text-xs">
                {getFileExtensionDisplayName(file)} file
              </CardDescription>
            </div>

            {/* Optional install action for .skill artifacts. */}
            {file.endsWith(".skill") && (
              <Button
                variant="ghost"
                size="sm"
                type="button"
                className="shrink-0"
                disabled={installingFile === file}
                onClick={(e) => handleInstallSkill(e, file)}
              >
                {installingFile === file ? (
                  <LoaderIcon className="size-4 animate-spin" />
                ) : (
                  <PackageIcon className="size-4" />
                )}
                {t.common.install}
              </Button>
            )}
          </div>
        </Card>
      ))}
    </ul>
  );
}
