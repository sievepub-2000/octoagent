"use client";

import { XIcon } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

import {
  ArtifactFileDetail,
  ArtifactFileList,
  useArtifacts,
} from "../artifacts";
import { useThread } from "../messages/context";

const ChatBox = ({
  children,
  threadId,
}: {
  children: ReactNode;
  threadId: string;
}) => {
  const { t } = useI18n();
  const { thread } = useThread();
  const {
    artifacts,
    deselect,
    open,
    select,
    selectedArtifact,
    setArtifacts,
    setOpen,
  } = useArtifacts();
  const previousThreadIdRef = useRef(threadId);

  useEffect(() => {
    if (previousThreadIdRef.current !== threadId) {
      previousThreadIdRef.current = threadId;
      deselect();
    }
    setArtifacts(thread.values.artifacts ?? []);
  }, [deselect, setArtifacts, thread.values.artifacts, threadId]);

  const panelVisible = open && artifacts.length > 0;

  return (
    <div className="relative flex size-full min-h-0 overflow-hidden">
      <div className="min-w-0 flex-1">{children}</div>
      {panelVisible && (
        <aside
          className={cn(
            "absolute inset-y-0 right-0 z-40 flex w-[min(92vw,430px)] flex-col border-l bg-background/96 shadow-[-18px_0_40px_var(--emboss-shadow)] backdrop-blur-xl",
            "lg:relative lg:z-auto lg:w-[400px] xl:w-[440px]",
          )}
          aria-label={t.common.artifacts}
        >
          <div className="flex h-14 shrink-0 items-center justify-between border-b px-4">
            <div className="min-w-0">
              <div className="text-sm font-semibold">{t.common.artifacts}</div>
              <div className="text-muted-foreground text-xs">
                {artifacts.length} {artifacts.length === 1 ? "file" : "files"}
              </div>
            </div>
            <Button
              aria-label={t.common.close}
              size="icon"
              variant="ghost"
              onClick={() => setOpen(false)}
            >
              <XIcon className="size-4" />
            </Button>
          </div>
          <div className="min-h-0 flex-1 overflow-auto p-4">
            {selectedArtifact ? (
              <ArtifactFileDetail
                className="h-full"
                filepath={selectedArtifact}
                threadId={threadId}
              />
            ) : (
              <ArtifactFileList
                files={artifacts}
                onSelect={(file) => select(file)}
                threadId={threadId}
              />
            )}
          </div>
        </aside>
      )}
    </div>
  );
};

export { ChatBox };
