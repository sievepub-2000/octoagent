"use client";

import { CirclePauseIcon, PlayIcon, SquareIcon } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import {
  useCreateTaskAgentMessage,
  useTaskAgentAction,
  useTaskAgentMessages,
  type AgentHandle,
} from "@/core/task-workspaces";

import { statusTone } from "./task-workspace-status";

export function AgentTranscript({
  taskId,
  agent,
}: {
  taskId: string;
  agent: AgentHandle;
}) {
  const [draft, setDraft] = useState("");
  const { messages, isLoading } = useTaskAgentMessages(taskId, agent.agent_id);
  const createMessage = useCreateTaskAgentMessage(taskId, agent.agent_id);
  const pauseAgent = useTaskAgentAction(taskId, agent.agent_id, "pause");
  const resumeAgent = useTaskAgentAction(taskId, agent.agent_id, "resume");
  const terminateAgent = useTaskAgentAction(taskId, agent.agent_id, "terminate");

  const sendMessage = async () => {
    const content = draft.trim();
    if (!content) {
      return;
    }
    await createMessage.mutateAsync({ content });
    setDraft("");
  };

  return (
    <div className="unified-flat-panel rounded-2xl border border-border/60 bg-muted/15 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-foreground">Agent transcript</div>
          <div className="text-xs text-muted-foreground">
            Directly inspect and steer the selected agent conversation.
          </div>
        </div>
        <Badge variant={statusTone(agent.status)}>{agent.status}</Badge>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button size="sm" type="button" variant="outline" onClick={() => pauseAgent.mutate()}>
          <CirclePauseIcon className="size-4" />
          Pause
        </Button>
        <Button size="sm" type="button" variant="outline" onClick={() => resumeAgent.mutate()}>
          <PlayIcon className="size-4" />
          Resume
        </Button>
        <Button size="sm" type="button" variant="outline" onClick={() => terminateAgent.mutate()}>
          <SquareIcon className="size-4" />
          Terminate
        </Button>
      </div>
      <ScrollArea className="mt-4 h-[260px] rounded-2xl border border-border/70 bg-muted/10 p-3">
        <div className="space-y-3 pr-3">
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading transcript…</p>
          ) : messages.length === 0 ? (
            <p className="text-sm text-muted-foreground">No transcript entries yet.</p>
          ) : (
            messages.map((message) => (
              <div className="space-y-1" key={message.message_id}>
                <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                  {message.role}
                </div>
                <div className="rounded-2xl border border-border/70 bg-background px-3 py-2 text-sm text-foreground">
                  {message.content}
                </div>
              </div>
            ))
          )}
        </div>
      </ScrollArea>
      <div className="mt-4 space-y-2">
        <Textarea
          className="min-h-28 resize-none"
          onChange={(event) => setDraft(event.target.value)}
          placeholder={`Direct message to ${agent.name}`}
          value={draft}
        />
        <Button
          onClick={sendMessage}
          size="sm"
          type="button"
          disabled={createMessage.isPending || draft.trim().length === 0}
        >
          Send
        </Button>
      </div>
    </div>
  );
}
