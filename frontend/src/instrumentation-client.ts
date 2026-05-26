import { installChunkLoadRecovery } from "@/core/runtime/chunk-recovery";

declare global {
  interface Window {
    __octoChunkLoadRecoveryInstalled?: boolean;
  }
}

if (!window.__octoChunkLoadRecoveryInstalled) {
  window.__octoChunkLoadRecoveryInstalled = true;
  installChunkLoadRecovery();
}