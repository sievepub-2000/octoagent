export type DialogueRouteKind =
  | "direct_answer"
  | "current_snapshot"
  | "current_research"
  | "tool_action"
  | "deep_agent";

export type DialogueRoute = {
  kind: DialogueRouteKind;
  reason: string;
  needsTools: boolean;
  needsMemory: boolean;
  needsDeepAgent: boolean;
};

const TOOL_ACTION_RE =
  /\b(shell|bash|powershell|ssh|scp|git|commit|push|deploy|run|execute|delete|remove|write|edit|create|build|test|open|read|file|repo|repository)\b/i;
const TOOL_ACTION_ZH_RE =
  /执行|运行|删除|修改|创建|部署|提交|同步|测试|修复|重构|检查|读取|文件|仓库|项目|主机|机器|继续|接着|接下来|下一步|然后|去做|开始干|开始执行|启动|按计划|完成它|完成任务|搞定|搞一下|落实|推进|推一下|做完|继续干/;
const CURRENT_WEATHER_RE = /\b(weather|forecast)\b|天气|天氣|氣象/i;
const CURRENT_X_TRENDS_RE =
  /(?=.*(?:\bx\.com\b|\btwitter\b|推特))(?=.*(?:\btrend\b|\bhot\b|热门|热点|趋势))/i;
const SYSTEM_TOOLS_RE =
  /\b(available tools?|tool inventory|tool status|system tools?)\b|系统工具|工具情况|可用工具|工具列表|工具清单|工具状态/i;
const CURRENT_RESEARCH_RE =
  /\b(today|latest|current|news|price|stock|weather|forecast|search|web|internet|lookup)\b|今天|最新|当前|現在|新闻|新聞|查询|搜尋|搜索|联网|网络/i;
const DEEP_RE =
  /\b(analy[sz]e|architecture|refactor|optimi[sz]e|design|plan|compare|investigate|debug|diagnose|complex|comprehensive)\b|深度|整体|架构|重构|优化|分析|评估|彻底|复杂|长期|多模块/i;

function route(kind: DialogueRouteKind, reason: string): DialogueRoute {
  return {
    kind,
    reason,
    needsTools: kind === "current_research" || kind === "tool_action" || kind === "deep_agent",
    needsMemory: kind === "tool_action" || kind === "deep_agent",
    needsDeepAgent: kind === "deep_agent",
  };
}

export function classifyDialogueRoute({
  text,
  mode,
  hasFiles,
}: {
  text: string;
  mode: string | null | undefined;
  hasFiles: boolean;
}): DialogueRoute {
  const trimmed = text.trim();
  if (hasFiles) return route("tool_action", "attachments_require_file_tools");
  if (mode === "thinking" || mode === "pro" || mode === "ultra") {
    return route("deep_agent", "user_selected_deep_mode");
  }
  if (!trimmed) return route("direct_answer", "empty_or_whitespace");
  if (TOOL_ACTION_RE.test(trimmed) || TOOL_ACTION_ZH_RE.test(trimmed)) {
    return route("tool_action", "action_or_workspace_keywords");
  }
  if (DEEP_RE.test(trimmed) || trimmed.length > 420) {
    return route("deep_agent", "deep_analysis_keywords_or_long_request");
  }
  if (
    CURRENT_WEATHER_RE.test(trimmed) ||
    CURRENT_X_TRENDS_RE.test(trimmed) ||
    SYSTEM_TOOLS_RE.test(trimmed)
  ) {
    return route("current_snapshot", "server_snapshot_supported_current_info");
  }
  if (CURRENT_RESEARCH_RE.test(trimmed)) {
    return route("current_research", "general_current_info_requires_research");
  }
  return route("direct_answer", "short_clear_question");
}
