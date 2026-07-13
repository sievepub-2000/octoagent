import { useQuery } from "@tanstack/react-query";
import { ActivityIcon, FilesIcon, PanelRightCloseIcon, PanelRightOpenIcon, ServerIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useArtifacts } from "@/components/workspace/artifacts";
import { ArtifactFileList } from "@/components/workspace/artifacts/artifact-file-list";
import { useThread } from "@/components/workspace/messages/context";
import { getJSON } from "@/core/api/http";
import type { RunEvent } from "@/core/runtime";

interface SystemOverview {
  overall: "ok" | "degraded";
  cpu: { percent: number };
  memory: { percent: number };
  disk: { percent: number };
  gpu: { name: string; utilization_percent: number; memory_used_mb: number; memory_total_mb: number; temperature_c: number; power_w: number } | null;
  temperatures: Array<{ name: string; temperature_c: number }>;
  services: Array<{ name: string; status: string }>;
  network: { proxy_configured: boolean; dns_over_tls: boolean };
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="flex items-center justify-between gap-4 border-b py-2 text-sm last:border-b-0"><span className="text-muted-foreground">{label}</span><span className="font-medium">{value}</span></div>;
}

function ContextPanel({ onClose, runEvents, threadId }: { onClose: () => void; runEvents: RunEvent[]; threadId: string }) {
  const { thread } = useThread();
  const [activeTab, setActiveTab] = useState("activity");
  const files = useMemo(() => thread.values.artifacts ?? [], [thread.values.artifacts]);
  const { setArtifacts } = useArtifacts();
  const system = useQuery({
    queryKey: ["system", "overview"],
    queryFn: () => getJSON<SystemOverview>("/api/system/overview"),
    enabled: activeTab === "system",
    staleTime: 10_000,
    refetchInterval: activeTab === "system" ? 15_000 : false,
  });

  useEffect(() => setArtifacts(files), [files, setArtifacts]);

  return (
    <aside className="flex size-full min-h-0 flex-col border-l bg-background">
      <div className="flex h-12 items-center justify-between border-b px-3"><span className="text-sm font-medium">Context</span><Button aria-label="Close context panel" size="icon-sm" variant="ghost" onClick={onClose}><PanelRightCloseIcon className="size-4" /></Button></div>
      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex min-h-0 flex-1 flex-col">
        <TabsList className="mx-3 mt-3 grid grid-cols-3"><TabsTrigger value="activity"><ActivityIcon className="size-3.5" /> Activity</TabsTrigger><TabsTrigger value="files"><FilesIcon className="size-3.5" /> Files</TabsTrigger><TabsTrigger value="system"><ServerIcon className="size-3.5" /> System</TabsTrigger></TabsList>
        <TabsContent value="activity" className="min-h-0 flex-1 overflow-y-auto p-3">
          {runEvents.length === 0 ? <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">Run activity will appear here.</p> : <ol className="space-y-2">{runEvents.slice().reverse().map((event, index) => <li key={`${event.id ?? "event"}-${index}`} className="rounded-lg border p-3"><p className="text-sm font-medium">{event.title}</p>{event.detail && <p className="mt-1 text-xs text-muted-foreground">{event.detail}</p>}</li>)}</ol>}
        </TabsContent>
        <TabsContent value="files" className="min-h-0 flex-1 overflow-y-auto p-3">{files.length > 0 ? <ArtifactFileList files={files} threadId={threadId} /> : <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">No generated files.</p>}</TabsContent>
        <TabsContent value="system" className="min-h-0 flex-1 overflow-y-auto p-3">
          {system.isLoading ? <p className="text-sm text-muted-foreground">Loading system status…</p> : system.data ? <div className="rounded-lg border px-3"><Metric label="Status" value={system.data.overall} /><Metric label="CPU" value={`${system.data.cpu.percent.toFixed(1)}%`} /><Metric label="Memory" value={`${system.data.memory.percent.toFixed(1)}%`} /><Metric label="Disk" value={`${system.data.disk.percent.toFixed(1)}%`} />{system.data.gpu && <><Metric label="GPU" value={`${system.data.gpu.utilization_percent.toFixed(0)}%`} /><Metric label="GPU temperature" value={`${system.data.gpu.temperature_c.toFixed(0)}°C`} /></>}<Metric label="Encrypted DNS" value={system.data.network.dns_over_tls ? "On" : "Off"} />{system.data.services.map((service) => <Metric key={service.name} label={service.name.replace(".service", "")} value={service.status} />)}</div> : <p className="text-sm text-destructive">System status unavailable.</p>}
        </TabsContent>
      </Tabs>
    </aside>
  );
}

const ChatBox: React.FC<{ children: React.ReactNode; isNewThread: boolean; mode: "flash" | "thinking" | "pro" | "ultra" | undefined; runEvents?: RunEvent[]; threadId: string; contextModelName?: string }> = ({ children, isNewThread, runEvents = [], threadId }) => {
  const { thread } = useThread();
  const [open, setOpen] = useState(!isNewThread);
  const hasContext = runEvents.length > 0 || (thread.values.artifacts?.length ?? 0) > 0;
  useEffect(() => { if (hasContext) setOpen(true); }, [hasContext]);
  return <div className="relative flex size-full min-h-0"><section className="relative min-w-0 flex-1">{children}{!open && <Button aria-label="Open context panel" className="absolute right-3 top-3 z-40" size="icon-sm" variant="outline" onClick={() => setOpen(true)}><PanelRightOpenIcon className="size-4" /></Button>}</section>{open && <div className="min-h-0 w-[min(34vw,28rem)] shrink-0"><ContextPanel onClose={() => setOpen(false)} runEvents={runEvents} threadId={threadId} /></div>}</div>;
};

export { ChatBox };
