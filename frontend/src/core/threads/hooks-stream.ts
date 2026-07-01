import type { AIMessage, Message, StreamMode } from "@langchain/langgraph-sdk";
import type { ThreadsClient } from "@langchain/langgraph-sdk/client";
import { useStream } from "@langchain/langgraph-sdk/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import type { PromptInputMessage } from "@/components/ai-elements/prompt-input";
import { pushSystemEvent } from "@/core/system-events/store";


import {
  getAPIClient,
  isRecoverableThreadMissingError,
  markThreadPersisted,
  markThreadProvisional,
} from "../api";
import { deleteJSON } from "../api/http";
import { getLangGraphBaseURL } from "../config";
import { useI18n } from "../i18n/hooks";
import type { FileInMessage } from "../messages/utils";
import { buildMlInternThreadContext, resolveMlInternProfile } from "../ml-intern/defaults";
import { planQueryOperation } from "../query-engine/api";
import { getRecursionLimit } from "../runtime-profile";
import { createRunEvent, normalizeRunEvent, type RunEvent } from "../runtime/run-events";
import type { LocalSettings } from "../settings";
import { useUpdateSubtask } from "../tasks/context";
import type { UploadedFileInfo } from "../uploads";
import { uploadFiles } from "../uploads";
import { createWorkflowEvent, useWorkflows } from "../workflows";

import {
  contextHandoffMatches,
  DEFAULT_STREAM_MODE,
  detectRecoverableIncompleteState,
  isDuplicateOptimisticHuman,
  isUnfinishedActionAnnouncement,
  lastMessage,
  MAX_PREPLAN_MESSAGE_CHARS,
  messageText,
  normalizeRuntimeMode,
  resolvePermissionMode,
  shouldEnableThinking,
} from "./hooks-utils";