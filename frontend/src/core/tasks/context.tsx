import type { Dispatch, SetStateAction } from "react";
import { createContext, useCallback, useContext, useMemo, useState } from "react";

import type { Subtask } from "./types";

export interface SubtaskContextValue {
  tasks: Record<string, Subtask>;
  setTasks: Dispatch<SetStateAction<Record<string, Subtask>>>;
}

export const SubtaskContext = createContext<SubtaskContextValue>({
  tasks: {},
  setTasks: () => {
    /* noop */
  },
});

export function SubtasksProvider({ children }: { children: React.ReactNode }) {
  const [tasks, setTasks] = useState<Record<string, Subtask>>({});
  const value = useMemo(() => ({ tasks, setTasks }), [tasks]);
  return (
    <SubtaskContext.Provider value={value}>
      {children}
    </SubtaskContext.Provider>
  );
}

export function useSubtaskContext() {
  const context = useContext(SubtaskContext);
  if (context === undefined) {
    throw new Error(
      "useSubtaskContext must be used within a SubtaskContext.Provider",
    );
  }
  return context;
}

export function useSubtask(id: string) {
  const { tasks } = useSubtaskContext();
  return tasks[id];
}

export function useUpdateSubtask() {
  const { setTasks } = useSubtaskContext();
  const updateSubtask = useCallback(
    (task: Partial<Subtask> & { id: string }) => {
      setTasks((current) => {
        const nextTask = { ...current[task.id], ...task } as Subtask;
        const existing = current[task.id];
        if (existing && shallowEqualSubtask(existing, nextTask)) {
          return current;
        }
        return {
          ...current,
          [task.id]: nextTask,
        };
      });
    },
    [setTasks],
  );
  return updateSubtask;
}

export function shallowEqualSubtask(a: Subtask, b: Subtask) {
  return (
    a.id === b.id &&
    a.status === b.status &&
    a.subagent_type === b.subagent_type &&
    a.description === b.description &&
    a.prompt === b.prompt &&
    a.result === b.result &&
    a.error === b.error &&
    a.latestMessage === b.latestMessage
  );
}
