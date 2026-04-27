import { useCallback, useEffect, useState } from "react";

import {
  getLocalSettings,
  LOCAL_SETTINGS_CHANGE_EVENT,
  saveLocalSettings,
  type LocalSettings,
} from "./local";

function isShallowEqualRecord(
  a: Record<string, unknown>,
  b: Record<string, unknown>,
): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const key of keys) {
    if (!Object.is(a[key], b[key])) {
      return false;
    }
  }
  return true;
}

export function useLocalSettings(): [
  LocalSettings,
  (
    key: keyof LocalSettings,
    value: Partial<LocalSettings[keyof LocalSettings]>,
  ) => void,
] {
  const [state, setState] = useState<LocalSettings>(() => getLocalSettings());

  // Sync state when another component updates localStorage via saveLocalSettings
  useEffect(() => {
    const handler = () => {
      setState(getLocalSettings());
    };
    window.addEventListener(LOCAL_SETTINGS_CHANGE_EVENT, handler);
    return () => window.removeEventListener(LOCAL_SETTINGS_CHANGE_EVENT, handler);
  }, []);

  const setter = useCallback(
    (
      key: keyof LocalSettings,
      value: Partial<LocalSettings[keyof LocalSettings]>,
    ) => {
      // Persist immediately so callers can safely navigate or unmount right
      // after updating settings without losing the write.
      const persistedState = getLocalSettings();
      const newState = {
        ...persistedState,
        [key]: {
          ...persistedState[key],
          ...value,
        },
      };

      if (
        isShallowEqualRecord(
          persistedState[key] as Record<string, unknown>,
          newState[key] as Record<string, unknown>,
        )
      ) {
        return;
      }

      saveLocalSettings(newState);
      setState(newState);
    },
    [],
  );
  return [state, setter];
}
