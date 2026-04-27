"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";

import {
  createWorkflow,
  type Workflow,
  type WorkflowEvent,
  type WorkflowConsoleTab,
  type WorkflowMode,
  type WorkflowTopTab,
} from "./types";

type WorkflowsContextValue = {
  workflows: Workflow[];
  selectedWorkflowId: string | null;
  selectedWorkflow: Workflow | null;
  events: WorkflowEvent[];
  topTab: WorkflowTopTab;
  consoleTab: WorkflowConsoleTab;
  consoleOpen: boolean;
  create: (mode: WorkflowMode) => void;
  update: (id: string, patch: Partial<Workflow>) => void;
  remove: (id: string) => void;
  select: (id: string) => void;
  hydrate: (workflows: Workflow[], events?: WorkflowEvent[]) => void;
  appendEvent: (event: WorkflowEvent) => void;
  setTopTab: (tab: WorkflowTopTab) => void;
  setConsoleTab: (tab: WorkflowConsoleTab) => void;
  setConsoleOpen: (open: boolean) => void;
};

const WorkflowsContext = createContext<WorkflowsContextValue | undefined>(
  undefined,
);

function isJsonEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

export function WorkflowsProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(
    null,
  );
  const [events, setEvents] = useState<WorkflowEvent[]>([]);
  const [topTab, setTopTab] = useState<WorkflowTopTab>("plan");
  const [consoleTab, setConsoleTab] = useState<WorkflowConsoleTab>("thinking");
  const [consoleOpen, setConsoleOpen] = useState(false);

  const selectedWorkflow =
    workflows.find((workflow) => workflow.id === selectedWorkflowId) ?? null;

  const create = useCallback((mode: WorkflowMode) => {
    const workflow = createWorkflow(mode);
    setWorkflows((prev) => [workflow, ...prev]);
    setSelectedWorkflowId(workflow.id);
    setTopTab("plan");
  }, []);

  const update = useCallback((id: string, patch: Partial<Workflow>) => {
    setWorkflows((prev) =>
      prev.map((workflow) =>
        workflow.id === id ? ({ ...workflow, ...patch } as Workflow) : workflow,
      ),
    );
  }, []);

  const remove = useCallback(
    (id: string) => {
      setWorkflows((prev) => prev.filter((workflow) => workflow.id !== id));
      setSelectedWorkflowId((prev) => (prev === id ? null : prev));
    },
    [],
  );

  const select = useCallback((id: string) => {
    setSelectedWorkflowId(id);
  }, []);

  const hydrate = useCallback((nextWorkflows: Workflow[], nextEvents: WorkflowEvent[] = []) => {
    setWorkflows((current) =>
      isJsonEqual(current, nextWorkflows) ? current : nextWorkflows,
    );
    setEvents((current) =>
      isJsonEqual(current, nextEvents) ? current : nextEvents,
    );
    setSelectedWorkflowId((prev) =>
      prev && nextWorkflows.some((workflow) => workflow.id === prev)
        ? prev
        : nextWorkflows[0]?.id ?? null,
    );
  }, []);

  const appendEvent = useCallback((event: WorkflowEvent) => {
    setEvents((prev) => [event, ...prev].slice(0, 100));
  }, []);

  const value = useMemo(
    () => ({
      workflows,
      selectedWorkflowId,
      selectedWorkflow,
      events,
      topTab,
      consoleTab,
      consoleOpen,
      create,
      update,
      remove,
      select,
      hydrate,
      appendEvent,
      setTopTab,
      setConsoleTab,
      setConsoleOpen,
    }),
    [
      workflows,
      selectedWorkflowId,
      selectedWorkflow,
      events,
      topTab,
      consoleTab,
      consoleOpen,
      create,
      update,
      remove,
      select,
      hydrate,
      appendEvent,
    ],
  );

  return (
    <WorkflowsContext.Provider value={value}>
      {children}
    </WorkflowsContext.Provider>
  );
}

export function useWorkflows() {
  const context = useContext(WorkflowsContext);
  if (!context) {
    throw new Error("useWorkflows must be used within a WorkflowsProvider");
  }
  return context;
}
