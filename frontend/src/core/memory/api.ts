import { getJSON } from "../api/http";

import type { UserMemory } from "./types";

export async function loadMemory() {
  return getJSON<UserMemory>("/api/memory");
}
