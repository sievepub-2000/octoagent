export type DialogueRouteKind =
  | "direct_answer"
  | "control_command"
  | "plan_only"
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
  /执行|运行|删除|修改|创建|部署|提交|同步|测试|修复|重构|检查|读取|文件|仓库|项目|主机|机器|去做|开始干|开始执行|启动|按计划|完成它|完成任务|搞定|搞一下|落实|推进|推一下|做完|继续干/;
const CONTROL_COMMAND_RE =
  /^\s*(?:\/(?:new|stop|pause|resume|continue|status)|(?:new|stop|pause|resume|continue|status)\s*)\s*$/i;
const CONTROL_COMMAND_ZH_RE =
  /^\s*(?:(?:开启|打开|新建|创建|开)(?:个|一个)?新(?:对话|会话|聊天)|新(?:对话|会话|聊天)|暂停|停止|停下|中止|取消|继续|接着|恢复|状态|进度|开启个新对话\/new|开启新对话\/new)\s*[。.!！?？]*\s*$/;
const PLAN_ONLY_RE =
  /\b(?:plan only|planning only|do not execute|don't execute|no execution|wait for confirmation|only analyze|only assess|proposal first|plan first)\b/i;
const PLAN_ONLY_ZH_RE =
  /先(?:给|出|写|提供|做)?(?:方案|计划|评估|分析|报告)|(?:等|待).{0,8}(?:我)?确认|确认后(?:再)?(?:执行|做|修改|开始)|不要(?:执行|动手|修改|提交|推送)|别(?:执行|动手|修改|提交|推送)|只(?:给|做|写)?(?:方案|计划|评估|分析|报告)|先评估|先分析|先不要(?:执行|动手|修改)/;
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
    needsMemory: kind === "plan_only" || kind === "tool_action" || kind === "deep_agent",
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
  if (CONTROL_COMMAND_RE.test(trimmed) || CONTROL_COMMAND_ZH_RE.test(trimmed)) {
    return route("control_command", "conversation_control_command");
  }
  if (PLAN_ONLY_RE.test(trimmed) || PLAN_ONLY_ZH_RE.test(trimmed)) {
    return route("plan_only", "planning_only_or_confirmation_gated");
  }
  if (TOOL_ACTION_RE.test(trimmed) || TOOL_ACTION_ZH_RE.test(trimmed)) {
    return route("tool_action", "action_or_workspace_keywords");
  }
  if (DEEP_RE.test(trimmed) || trimmed.length > 420) {
    return route("deep_agent", "deep_analysis_keywords_or_long_request");
  }
  if (CURRENT_WEATHER_RE.test(trimmed)) {
    return route("current_research", "weather_requires_current_research");
  }
  if (CURRENT_X_TRENDS_RE.test(trimmed) || SYSTEM_TOOLS_RE.test(trimmed)) {
    return route("current_snapshot", "server_snapshot_supported_current_info");
  }
  if (CURRENT_RESEARCH_RE.test(trimmed)) {
    return route("current_research", "general_current_info_requires_research");
  }
  return route("direct_answer", "short_clear_question");
}
