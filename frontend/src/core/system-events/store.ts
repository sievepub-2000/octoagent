"use client";

/**
 * System events store — non-fatal status/info/warning notifications shown in
 * the system-events sheet instead of as transient toasts.
 *
 * Implemented with a tiny pub/sub + React.useSyncExternalStore so we don't
 * pull in zustand (which is not in this project's dependency closure).
 *
 * Persistence: latest events + unreadCount are mirrored to localStorage so the
 * notification panel survives page reloads.
 */

import { useSyncExternalStore } from "react";

export type SystemEventLevel = "info" | "warning" | "error" | "success";

export interface SystemEvent {
  id: string;
  level: SystemEventLevel;
  message: string;
  detail?: string;
  source?: string;
  timestamp: number;
}

interface SystemEventsState {
  events: SystemEvent[];
  unreadCount: number;
}

const MAX_EVENTS = 200;
const STORAGE_KEY = "octoagent.system-events.v1";
let _nextId = 1;

function _loadFromStorage(): SystemEventsState {
  if (typeof window === "undefined") return { events: [], unreadCount: 0 };
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { events: [], unreadCount: 0 };
    const parsed = JSON.parse(raw) as SystemEventsState;
    const events = Array.isArray(parsed.events) ? parsed.events.slice(0, MAX_EVENTS) : [];
    const unreadCount = Number.isFinite(parsed.unreadCount)
      ? Math.max(0, Math.min(parsed.unreadCount, events.length))
      : 0;
    return { events, unreadCount };
  } catch {
    return { events: [], unreadCount: 0 };
  }
}

let state: SystemEventsState = _loadFromStorage();
let _hydrated = typeof window !== "undefined";
const listeners = new Set<() => void>();

function _persist(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* quota or privacy mode — drop silently */
  }
}

function getSnapshot(): SystemEventsState {
  return state;
}

const _serverSnapshot: SystemEventsState = { events: [], unreadCount: 0 };
function getServerSnapshot(): SystemEventsState {
  return _serverSnapshot;
}

function subscribe(listener: () => void): () => void {
  if (!_hydrated && typeof window !== "undefined") {
    state = _loadFromStorage();
    _hydrated = true;
  }
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function emit(): void {
  _persist();
  for (const listener of listeners) listener();
}

export function pushSystemEvent(
  event: Omit<SystemEvent, "id" | "timestamp">,
): void {
  const next: SystemEvent = {
    id: `sysev-${_nextId++}-${Date.now().toString(36)}`,
    timestamp: Date.now(),
    ...event,
  };
  const events = [next, ...state.events].slice(0, MAX_EVENTS);
  state = { events, unreadCount: state.unreadCount + 1 };
  emit();
}

export function markAllSystemEventsRead(): void {
  if (state.unreadCount === 0) return;
  state = { ...state, unreadCount: 0 };
  emit();
}

export function clearSystemEvents(): void {
  if (state.events.length === 0 && state.unreadCount === 0) return;
  state = { events: [], unreadCount: 0 };
  emit();
}

export function useSystemEvents(): SystemEventsState {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
