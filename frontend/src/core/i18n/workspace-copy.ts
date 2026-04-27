import type { Locale } from "@/core/i18n";

type ModelFieldCopy = {
  configName: string;
  displayName: string;
  providerModel: string;
  interfaceType: string;
  providerName: string;
  customUsePath: string;
  apiKey: string;
  baseUrl: string;
  googleApiKey: string;
  fallbackModels: string;
  maxContextTokens: string;
  description: string;
  thinking: string;
  reasoning: string;
  vision: string;
  descriptionPlaceholder: string;
};

type WelcomeCopy = {
  workspaceBadge: string;
  continuationFromSource: (source: string, count: number) => string;
  continuationFromPrior: string;
};

type AgentWelcomeCopy = {
  identityPrompt: string;
};

type SetupWizardCopy = {
  progressBadge: string;
  workspaceLayoutDefault: string;
  workspaceLayoutEnv: string;
  workspaceLayoutTaskwork: string;
  modelOnlyStepDesc: string;
  defaultModelNotice: string;
  selected: string;
  modelRequiredError: string;
  createFirstModelFailed: string;
  finishRequiresModel: string;
  setupFailed: string;
  createFirstModelTitle: string;
  createFirstModelDesc: string;
  createFirstModelFootnote: string;
  createModel: string;
  creatingModel: string;
  openFullModelSettings: string;
  firstRunChecklistTitle: string;
  checklistModelTitle: string;
  checklistModelDesc: string;
  checklistFinishTitle: string;
  checklistFinishDesc: string;
  checklistAdjustTitle: string;
  checklistAdjustDesc: string;
  applySetupTitle: string;
  applySetupDesc: string;
  workspaceLabel: string;
  defaultModelLabel: string;
  providerLabel: string;
  interfaceLabel: string;
};

type ModelsPageCopy = {
  pageDescription: string;
  addModel: string;
  editModel: string;
  formHint: string;
  editSelected: string;
  requiredError: string;
  modelUpdated: string;
  modelCreated: string;
  saveFailed: string;
  saveChanges: string;
  createModel: string;
  reset: string;
  noModels: string;
  backup: string;
  editModelTitle: string;
  deleteConfirm: (name: string) => string;
  modelDeleted: string;
  deleteFailed: string;
  contextBadge: (thousands: number) => string;
  fallbackBadge: (count: number) => string;
  nameLabel: string;
  interfaceLabel: string;
  providerLabel: string;
  customUseLabel: string;
  descriptionLabel: string;
  thinkingLabel: string;
  reasoningLabel: string;
  visionLabel: string;
  contextWindowLabel: string;
  fallbackChainLabel: string;
  yes: string;
  no: string;
};

type TaskWorkspaceCopy = {
  template: string;
  currentPhase: string;
  missingInputs: string;
  none: string;
  addGoalForBrain: string;
  topologyTitle: string;
  topologyDescription: string;
  taskMode: string;
  agentCount: string;
  selectedRuntime: string;
  capabilityAlignmentTitle: string;
  capabilityAlignmentDescription: string;
  runtimeLabel: string;
  loadingRuntime: string;
  systemExecutionLabel: string;
  loadingSystemExecution: string;
  policySurfaceLabel: string;
  loadingPermissionPolicy: string;
  serverCliLabel: string;
  serverCliDescription: string;
  systemCliBlocked: string;
  policyEnforcedNote: string;
  brainCompilationLabel: string;
  compilingPlan: string;
  cardDetailsTitle: string;
  cardDetailsDescription: string;
  noCardDescription: string;
  boundAgentLabel: string;
  permissionLabel: string;
  agentRoleLabel: string;
  modelLabel: string;
  documentRoleLabel: string;
  canvasPositionLabel: string;
  branchTaskLabel: string;
  promptPreviewLabel: string;
  archiveDocumentsLabel: string;
  selectCardHint: string;
};

type TaskRuntimeCopy = {
  workflowCompiledTitle: string;
  workflowCompiledDetail: string;
  workflowStartedTitle: string;
  workflowStartedDetail: string;
  workflowPausedTitle: string;
  workflowPausedDetail: string;
  workflowResumedTitle: string;
  workflowResumedDetail: string;
  workflowTerminatedTitle: string;
  workflowTerminatedDetail: string;
  workflowGraphUpdatedTitle: string;
  workflowGraphUpdatedDetail: string;
  noWorkflowRuntimeTitle: string;
  noWorkflowRuntimeDescription: string;
  selectRuntimeTitle: string;
  selectRuntimeDescription: string;
  loadingRuntimeTitle: string;
  loadingRuntimeDescription: string;
  noGoalProvided: string;
  linkedBadge: string;
  openPage: string;
  modeLabel: string;
  progressLabel: string;
  threadBindingLabel: string;
  linkedToThisChat: string;
  visibleGlobally: string;
  agentsTitle: string;
  agentsDescription: string;
  noAgentsRegistered: string;
  checkpointsTitle: string;
  checkpointsDescription: string;
  noCheckpoints: string;
  realWorkflowRuntimeTitle: string;
  realWorkflowRuntimeDescription: string;
  workflowNameLabel: string;
  goalLabel: string;
  modeSelectLabel: string;
  createFromChatContext: string;
  linkedWorkflowsCount: (count: number) => string;
  noLinkedWorkflows: string;
};

type WorkspaceLocaleCopy = {
  modelFields: ModelFieldCopy;
  welcome: WelcomeCopy;
  agentWelcome: AgentWelcomeCopy;
  setupWizard: SetupWizardCopy;
  modelsPage: ModelsPageCopy;
  taskWorkspace: TaskWorkspaceCopy;
  taskRuntime: TaskRuntimeCopy;
};

const modelFields: Record<Locale, ModelFieldCopy> = {
  "en-US": {
    configName: "Config name",
    displayName: "Display name",
    providerModel: "Provider model",
    interfaceType: "Interface type",
    providerName: "Provider name",
    customUsePath: "Custom use path",
    apiKey: "API key / env ref",
    baseUrl: "Base URL",
    googleApiKey: "Google API key",
    fallbackModels: "Fallback models",
    maxContextTokens: "Max context tokens",
    description: "Description",
    thinking: "Thinking",
    reasoning: "Reasoning",
    vision: "Vision",
    descriptionPlaceholder: "Operator-facing description for this model entry.",
  },
  "ja": {
    configName: "設定名",
    displayName: "表示名",
    providerModel: "プロバイダーモデル",
    interfaceType: "インターフェース種別",
    providerName: "プロバイダー名",
    customUsePath: "カスタム use パス",
    apiKey: "API キー / 環境変数参照",
    baseUrl: "Base URL",
    googleApiKey: "Google API キー",
    fallbackModels: "フォールバックモデル",
    maxContextTokens: "最大コンテキストトークン",
    description: "説明",
    thinking: "思考",
    reasoning: "推論",
    vision: "視覚",
    descriptionPlaceholder: "このモデル項目の運用向け説明を入力します。",
  },
  "ko": {
    configName: "구성 이름",
    displayName: "표시 이름",
    providerModel: "제공자 모델",
    interfaceType: "인터페이스 유형",
    providerName: "제공자 이름",
    customUsePath: "사용자 정의 use 경로",
    apiKey: "API 키 / 환경 변수 참조",
    baseUrl: "Base URL",
    googleApiKey: "Google API 키",
    fallbackModels: "폴백 모델",
    maxContextTokens: "최대 컨텍스트 토큰",
    description: "설명",
    thinking: "사고",
    reasoning: "추론",
    vision: "비전",
    descriptionPlaceholder: "이 모델 항목에 대한 운영 설명을 입력하세요.",
  },
  "zh-CN": {
    configName: "配置名称",
    displayName: "显示名称",
    providerModel: "提供方模型",
    interfaceType: "接口类型",
    providerName: "提供方名称",
    customUsePath: "自定义 use 路径",
    apiKey: "API Key / 环境变量引用",
    baseUrl: "基础 URL",
    googleApiKey: "Google API Key",
    fallbackModels: "降级模型链",
    maxContextTokens: "最大上下文 Token",
    description: "描述",
    thinking: "思考",
    reasoning: "推理",
    vision: "视觉",
    descriptionPlaceholder: "用于说明该模型条目的运营备注。",
  },
  "zh-TW": {
    configName: "設定名稱",
    displayName: "顯示名稱",
    providerModel: "提供方模型",
    interfaceType: "介面類型",
    providerName: "提供方名稱",
    customUsePath: "自訂 use 路徑",
    apiKey: "API Key / 環境變數參照",
    baseUrl: "基礎 URL",
    googleApiKey: "Google API Key",
    fallbackModels: "降級模型鏈",
    maxContextTokens: "最大上下文 Token",
    description: "描述",
    thinking: "思考",
    reasoning: "推理",
    vision: "視覺",
    descriptionPlaceholder: "用於說明該模型條目的營運備註。",
  },
};

const welcomeCopy: Record<Locale, WelcomeCopy> = {
  "en-US": {
    workspaceBadge: "OctoAgent Workspace",
    continuationFromSource: (source: string, count: number) =>
      `Continuing from \"${source}\" (${count} messages)`,
    continuationFromPrior: "Continuing from prior conversation",
  },
  "ja": {
    workspaceBadge: "OctoAgent ワークスペース",
    continuationFromSource: (source: string, count: number) =>
      `\"${source}\" から継続中 (${count} 件のメッセージ)`,
    continuationFromPrior: "前の会話から継続中",
  },
  "ko": {
    workspaceBadge: "OctoAgent 워크스페이스",
    continuationFromSource: (source: string, count: number) =>
      `\"${source}\"에서 이어지는 중 (${count}개 메시지)`,
    continuationFromPrior: "이전 대화에서 이어지는 중",
  },
  "zh-CN": {
    workspaceBadge: "OctoAgent 工作区",
    continuationFromSource: (source: string, count: number) =>
      `延续自“${source}” (${count} 条消息)`,
    continuationFromPrior: "延续自上一段对话",
  },
  "zh-TW": {
    workspaceBadge: "OctoAgent 工作區",
    continuationFromSource: (source: string, count: number) =>
      `延續自「${source}」 (${count} 則訊息)`,
    continuationFromPrior: "延續自上一段對話",
  },
};

const agentWelcomeCopy: Record<Locale, AgentWelcomeCopy> = {
  "en-US": {
    identityPrompt: "Identity Prompt",
  },
  ja: {
    identityPrompt: "身份提示词",
  },
  ko: {
    identityPrompt: "身份提示词",
  },
  "zh-CN": {
    identityPrompt: "身份提示词",
  },
  "zh-TW": {
    identityPrompt: "身份提示詞",
  },
};

const setupWizardCopy: Record<Locale, SetupWizardCopy> = {
  "en-US": {
    progressBadge: "1 / 1 Model Configuration",
    workspaceLayoutDefault: "default/ : everyday chats, threads, and user context",
    workspaceLayoutEnv: "env/ : initialization settings and environment snapshots",
    workspaceLayoutTaskwork: "workflow/taskwork/ : all workflow task directories",
    modelOnlyStepDesc:
      "Keep exactly one onboarding step: pick the default chat model, and use the same model as the workflow execution default.",
    defaultModelNotice:
      "The selected model becomes the default for new chats and workflow runs. You can still override it later from the chat input or agent-specific settings.",
    selected: "Selected",
    modelRequiredError: "Config name and provider model are required.",
    createFirstModelFailed: "Failed to create the first model.",
    finishRequiresModel: "Create at least one model before finishing setup.",
    setupFailed: "Setup failed",
    createFirstModelTitle: "Create the first model",
    createFirstModelDesc:
      "No model is configured yet. Fill in the model card below to add the first model, then finish setup.",
    createFirstModelFootnote:
      "This reuses the full model settings capability, reduced to the core fields needed for first-run onboarding.",
    createModel: "Create first model",
    creatingModel: "Creating model...",
    openFullModelSettings: "Open full model settings",
    firstRunChecklistTitle: "First-run checklist",
    checklistModelTitle: "1. Add one valid model entry",
    checklistModelDesc:
      "At minimum, provide a config name and a provider model. Prefer interface-first fields over a raw class path.",
    checklistFinishTitle: "2. Finish setup",
    checklistFinishDesc:
      "The created model is selected automatically and written into setup state as the default for chat and workflows.",
    checklistAdjustTitle: "3. Adjust later if needed",
    checklistAdjustDesc:
      "You can still manage the full model pool later from the standalone model settings page.",
    applySetupTitle: "Apply setup",
    applySetupDesc:
      "Persist the workspace layout and selected default model. Other initialization steps are intentionally removed.",
    workspaceLabel: "Workspace",
    defaultModelLabel: "Default model",
    providerLabel: "Provider",
    interfaceLabel: "Interface",
  },
  "ja": {
    progressBadge: "1 / 1 モデル設定",
    workspaceLayoutDefault: "default/ : 日常会話、スレッド、ユーザーコンテキスト",
    workspaceLayoutEnv: "env/ : 初期設定と環境スナップショット",
    workspaceLayoutTaskwork: "workflow/taskwork/ : すべてのワークフロータスクディレクトリ",
    modelOnlyStepDesc:
      "初期設定は 1 ステップだけに絞ります。既定の会話モデルを選び、そのままワークフロー実行の既定モデルとして使います。",
    defaultModelNotice:
      "選択したモデルは新規チャットとワークフロー実行の既定になります。後から入力欄やエージェント設定で上書きできます。",
    selected: "選択済み",
    modelRequiredError: "設定名とプロバイダーモデルは必須です。",
    createFirstModelFailed: "最初のモデル作成に失敗しました。",
    finishRequiresModel: "セットアップ完了前に、少なくとも 1 つのモデルを作成してください。",
    setupFailed: "セットアップに失敗しました",
    createFirstModelTitle: "最初のモデルを作成",
    createFirstModelDesc:
      "まだモデルが設定されていません。以下のモデルカードに入力して最初のモデルを追加し、その後セットアップを完了してください。",
    createFirstModelFootnote:
      "完全なモデル設定機能を再利用しつつ、初回オンボーディングに必要な項目だけへ絞っています。",
    createModel: "最初のモデルを作成",
    creatingModel: "モデルを作成中...",
    openFullModelSettings: "完全なモデル設定を開く",
    firstRunChecklistTitle: "初回チェックリスト",
    checklistModelTitle: "1. 有効なモデルを 1 つ追加",
    checklistModelDesc:
      "最低限、設定名とプロバイダーモデルを入力してください。生のクラスパスより、interface_type などのインターフェース項目を優先します。",
    checklistFinishTitle: "2. セットアップを完了",
    checklistFinishDesc:
      "作成したモデルは自動で選択され、チャットとワークフローの既定としてセットアップ状態に保存されます。",
    checklistAdjustTitle: "3. 必要なら後で調整",
    checklistAdjustDesc:
      "後から独立したモデル設定ページで完全なモデルプールを管理できます。",
    applySetupTitle: "セットアップを適用",
    applySetupDesc:
      "ワークスペース構成と選択した既定モデルを保存します。その他の初期化手順は意図的に削除されています。",
    workspaceLabel: "ワークスペース",
    defaultModelLabel: "既定モデル",
    providerLabel: "プロバイダー",
    interfaceLabel: "インターフェース",
  },
  "ko": {
    progressBadge: "1 / 1 모델 구성",
    workspaceLayoutDefault: "default/ : 일상 대화, 스레드, 사용자 컨텍스트",
    workspaceLayoutEnv: "env/ : 초기화 설정 및 환경 스냅샷",
    workspaceLayoutTaskwork: "workflow/taskwork/ : 모든 워크플로 작업 디렉터리",
    modelOnlyStepDesc:
      "초기화는 한 단계만 남깁니다. 기본 대화 모델을 고르고, 같은 모델을 워크플로 실행 기본값으로 사용합니다.",
    defaultModelNotice:
      "선택한 모델은 새 대화와 워크플로 실행의 기본값이 됩니다. 이후 입력창이나 에이전트 설정에서 별도로 덮어쓸 수 있습니다.",
    selected: "선택됨",
    modelRequiredError: "구성 이름과 제공자 모델은 필수입니다.",
    createFirstModelFailed: "첫 번째 모델 생성에 실패했습니다.",
    finishRequiresModel: "설정을 마치기 전에 최소 하나의 모델을 만드세요.",
    setupFailed: "설정에 실패했습니다",
    createFirstModelTitle: "첫 번째 모델 만들기",
    createFirstModelDesc:
      "아직 구성된 모델이 없습니다. 아래 모델 카드를 작성해 첫 번째 모델을 만든 뒤 설정을 마무리하세요.",
    createFirstModelFootnote:
      "전체 모델 설정 기능을 재사용하되, 첫 실행 온보딩에 필요한 핵심 필드만 남겼습니다.",
    createModel: "첫 번째 모델 만들기",
    creatingModel: "모델 생성 중...",
    openFullModelSettings: "전체 모델 설정 열기",
    firstRunChecklistTitle: "첫 실행 체크리스트",
    checklistModelTitle: "1. 유효한 모델 하나 추가",
    checklistModelDesc:
      "최소한 구성 이름과 제공자 모델을 입력하세요. 원시 클래스 경로보다 interface_type 같은 인터페이스 필드를 우선하는 편이 좋습니다.",
    checklistFinishTitle: "2. 설정 완료",
    checklistFinishDesc:
      "생성한 모델은 자동으로 선택되어 채팅과 워크플로의 기본값으로 설정 상태에 기록됩니다.",
    checklistAdjustTitle: "3. 필요하면 나중에 조정",
    checklistAdjustDesc:
      "이후 독립된 모델 설정 페이지에서 전체 모델 풀을 계속 관리할 수 있습니다.",
    applySetupTitle: "설정 적용",
    applySetupDesc:
      "워크스페이스 레이아웃과 선택한 기본 모델을 저장합니다. 다른 초기화 단계는 의도적으로 제거되었습니다.",
    workspaceLabel: "워크스페이스",
    defaultModelLabel: "기본 모델",
    providerLabel: "제공자",
    interfaceLabel: "인터페이스",
  },
  "zh-CN": {
    progressBadge: "1 / 1 模型配置",
    workspaceLayoutDefault: "default/ : 日常对话、线程、用户上下文",
    workspaceLayoutEnv: "env/ : 初始化设置与环境快照",
    workspaceLayoutTaskwork: "workflow/taskwork/ : 所有 workflow 任务目录",
    modelOnlyStepDesc:
      "初始化只保留一个步骤：选择默认对话模型，并同时作为工作流执行默认模型。",
    defaultModelNotice:
      "所选模型会同时作为新对话和工作流运行的默认模型。之后仍可在输入框或智能体设置中单独覆盖。",
    selected: "已选择",
    modelRequiredError: "配置名称和提供方模型为必填项。",
    createFirstModelFailed: "创建第一个模型失败。",
    finishRequiresModel: "请先创建至少一个模型，再完成初始化。",
    setupFailed: "初始化失败",
    createFirstModelTitle: "创建第一个模型",
    createFirstModelDesc:
      "当前还没有配置模型。先填写下面的模型配置卡片，创建第一个模型后再完成初始化。",
    createFirstModelFootnote:
      "这里复用了完整模型设置页的能力，但收敛为首次启动所需的核心字段。",
    createModel: "创建第一个模型",
    creatingModel: "创建模型中...",
    openFullModelSettings: "打开完整模型设置",
    firstRunChecklistTitle: "首次使用检查清单",
    checklistModelTitle: "1. 新增一个可用模型",
    checklistModelDesc:
      "至少填写配置名称和提供方模型。优先使用 interface_type 等接口字段，而不是原始类路径。",
    checklistFinishTitle: "2. 完成初始化",
    checklistFinishDesc:
      "新建的模型会自动写入初始化状态，并作为对话和工作流的默认模型。",
    checklistAdjustTitle: "3. 之后按需调整",
    checklistAdjustDesc:
      "后续仍可在独立的模型设置页中维护完整模型池。",
    applySetupTitle: "应用初始化配置",
    applySetupDesc:
      "保存工作区布局和所选默认模型。其余初始化步骤已按要求移除。",
    workspaceLabel: "工作区",
    defaultModelLabel: "默认模型",
    providerLabel: "提供方",
    interfaceLabel: "接口",
  },
  "zh-TW": {
    progressBadge: "1 / 1 模型設定",
    workspaceLayoutDefault: "default/ : 日常對話、執行緒、使用者上下文",
    workspaceLayoutEnv: "env/ : 初始化設定與環境快照",
    workspaceLayoutTaskwork: "workflow/taskwork/ : 所有 workflow 任務目錄",
    modelOnlyStepDesc:
      "初始化只保留一個步驟：選擇預設對話模型，並同時作為工作流執行預設模型。",
    defaultModelNotice:
      "所選模型會同時作為新對話與工作流執行的預設模型。之後仍可在輸入框或代理設定中個別覆寫。",
    selected: "已選擇",
    modelRequiredError: "設定名稱和提供方模型為必填項。",
    createFirstModelFailed: "建立第一個模型失敗。",
    finishRequiresModel: "請先建立至少一個模型，再完成初始化。",
    setupFailed: "初始化失敗",
    createFirstModelTitle: "建立第一個模型",
    createFirstModelDesc:
      "目前還沒有設定模型。先填寫下面的模型設定卡片，建立第一個模型後再完成初始化。",
    createFirstModelFootnote:
      "這裡重用了完整模型設定頁的能力，但收斂為首次啟動所需的核心欄位。",
    createModel: "建立第一個模型",
    creatingModel: "建立模型中...",
    openFullModelSettings: "開啟完整模型設定",
    firstRunChecklistTitle: "首次使用檢查清單",
    checklistModelTitle: "1. 新增一個可用模型",
    checklistModelDesc:
      "至少填寫設定名稱與提供方模型。優先使用 interface_type 等介面欄位，而不是原始類別路徑。",
    checklistFinishTitle: "2. 完成初始化",
    checklistFinishDesc:
      "新建的模型會自動寫入初始化狀態，並作為對話與工作流的預設模型。",
    checklistAdjustTitle: "3. 之後按需調整",
    checklistAdjustDesc:
      "後續仍可在獨立的模型設定頁中維護完整模型池。",
    applySetupTitle: "套用初始化設定",
    applySetupDesc:
      "保存工作區布局與所選預設模型。其餘初始化步驟已依要求移除。",
    workspaceLabel: "工作區",
    defaultModelLabel: "預設模型",
    providerLabel: "提供方",
    interfaceLabel: "介面",
  },
};

const modelsPageCopy: Record<Locale, ModelsPageCopy> = {
  "en-US": {
    pageDescription:
      "Manage model entries with interface-first fields so onboarding no longer depends on raw provider class strings.",
    addModel: "Add model",
    editModel: "Edit model",
    formHint:
      "Prefer interface_type + provider_name. Use the raw use path only for a custom wrapper.",
    editSelected: "Edit selected",
    requiredError: "Model name and provider model are required.",
    modelUpdated: "Model updated.",
    modelCreated: "Model created.",
    saveFailed: "Failed to save model.",
    saveChanges: "Save changes",
    createModel: "Create model",
    reset: "Reset",
    noModels: "No models available.",
    backup: "Emergency backup",
    editModelTitle: "Edit model",
    deleteConfirm: (name: string) => `Delete model \"${name}\"?`,
    modelDeleted: "Model deleted.",
    deleteFailed: "Failed to delete model.",
    contextBadge: (thousands: number) => `${thousands}K ctx`,
    fallbackBadge: (count: number) => `${count} fallback${count === 1 ? "" : "s"}`,
    nameLabel: "Name",
    interfaceLabel: "Interface",
    providerLabel: "Provider",
    customUseLabel: "Custom use",
    descriptionLabel: "Description",
    thinkingLabel: "Thinking",
    reasoningLabel: "Reasoning effort",
    visionLabel: "Vision",
    contextWindowLabel: "Context window",
    fallbackChainLabel: "Fallback chain",
    yes: "Yes",
    no: "No",
  },
  "ja": {
    pageDescription:
      "インターフェース優先の項目でモデルエントリを管理し、オンボーディングが生の provider class 文字列に依存しないようにします。",
    addModel: "モデルを追加",
    editModel: "モデルを編集",
    formHint:
      "interface_type と provider_name を優先してください。生の use パスはカスタムラッパー時のみ使用します。",
    editSelected: "選択中を編集",
    requiredError: "モデル名とプロバイダーモデルは必須です。",
    modelUpdated: "モデルを更新しました。",
    modelCreated: "モデルを作成しました。",
    saveFailed: "モデルの保存に失敗しました。",
    saveChanges: "変更を保存",
    createModel: "モデルを作成",
    reset: "リセット",
    noModels: "利用可能なモデルがありません。",
    backup: "緊急備援模型",
    editModelTitle: "モデルを編集",
    deleteConfirm: (name: string) => `モデル「${name}」を削除しますか？`,
    modelDeleted: "モデルを削除しました。",
    deleteFailed: "モデルの削除に失敗しました。",
    contextBadge: (thousands: number) => `${thousands}K コンテキスト`,
    fallbackBadge: (count: number) => `フォールバック ${count} 件`,
    nameLabel: "名称",
    interfaceLabel: "インターフェース",
    providerLabel: "プロバイダー",
    customUseLabel: "カスタム use",
    descriptionLabel: "説明",
    thinkingLabel: "思考",
    reasoningLabel: "推論能力",
    visionLabel: "視覚",
    contextWindowLabel: "コンテキスト幅",
    fallbackChainLabel: "フォールバック連鎖",
    yes: "はい",
    no: "いいえ",
  },
  "ko": {
    pageDescription:
      "인터페이스 우선 필드로 모델 항목을 관리해 온보딩이 원시 provider class 문자열에 더 이상 의존하지 않도록 합니다.",
    addModel: "모델 추가",
    editModel: "모델 편집",
    formHint:
      "interface_type 과 provider_name 을 우선 사용하세요. 원시 use 경로는 사용자 정의 래퍼에서만 필요합니다.",
    editSelected: "선택 항목 편집",
    requiredError: "모델 이름과 제공자 모델은 필수입니다.",
    modelUpdated: "모델이 업데이트되었습니다.",
    modelCreated: "모델이 생성되었습니다.",
    saveFailed: "모델 저장에 실패했습니다.",
    saveChanges: "변경 저장",
    createModel: "모델 만들기",
    reset: "초기화",
    noModels: "사용 가능한 모델이 없습니다.",
    backup: "긴급 백업 모델",
    editModelTitle: "모델 편집",
    deleteConfirm: (name: string) => `\"${name}\" 모델을 삭제할까요?`,
    modelDeleted: "모델이 삭제되었습니다.",
    deleteFailed: "모델 삭제에 실패했습니다.",
    contextBadge: (thousands: number) => `${thousands}K 컨텍스트`,
    fallbackBadge: (count: number) => `폴백 ${count}개`,
    nameLabel: "이름",
    interfaceLabel: "인터페이스",
    providerLabel: "제공자",
    customUseLabel: "사용자 정의 use",
    descriptionLabel: "설명",
    thinkingLabel: "사고",
    reasoningLabel: "추론 능력",
    visionLabel: "비전",
    contextWindowLabel: "컨텍스트 창",
    fallbackChainLabel: "폴백 체인",
    yes: "예",
    no: "아니오",
  },
  "zh-CN": {
    pageDescription:
      "使用接口优先字段维护模型条目，避免初始化再依赖原始 provider class 字符串。",
    addModel: "新增模型",
    editModel: "编辑模型",
    formHint:
      "优先填写 interface_type + provider_name。只有自定义封装时才需要原始 use 路径。",
    editSelected: "编辑当前选中项",
    requiredError: "模型名称和提供方模型为必填项。",
    modelUpdated: "模型已更新。",
    modelCreated: "模型已创建。",
    saveFailed: "保存模型失败。",
    saveChanges: "保存更改",
    createModel: "创建模型",
    reset: "重置",
    noModels: "当前没有可用模型。",
    backup: "应急备用模型",
    editModelTitle: "编辑模型",
    deleteConfirm: (name: string) => `确定要删除模型“${name}”吗？`,
    modelDeleted: "模型已删除。",
    deleteFailed: "删除模型失败。",
    contextBadge: (thousands: number) => `${thousands}K 上下文`,
    fallbackBadge: (count: number) => `${count} 个降级模型`,
    nameLabel: "名称",
    interfaceLabel: "接口",
    providerLabel: "提供方",
    customUseLabel: "自定义 use",
    descriptionLabel: "描述",
    thinkingLabel: "思考",
    reasoningLabel: "推理能力",
    visionLabel: "视觉",
    contextWindowLabel: "上下文窗口",
    fallbackChainLabel: "降级链路",
    yes: "是",
    no: "否",
  },
  "zh-TW": {
    pageDescription:
      "使用介面優先欄位維護模型條目，避免初始化再依賴原始 provider class 字串。",
    addModel: "新增模型",
    editModel: "編輯模型",
    formHint:
      "優先填寫 interface_type + provider_name。只有自訂封裝時才需要原始 use 路徑。",
    editSelected: "編輯目前選中項",
    requiredError: "模型名稱和提供方模型為必填項。",
    modelUpdated: "模型已更新。",
    modelCreated: "模型已建立。",
    saveFailed: "保存模型失敗。",
    saveChanges: "保存變更",
    createModel: "建立模型",
    reset: "重置",
    noModels: "目前沒有可用模型。",
    backup: "緊急備援模型",
    editModelTitle: "編輯模型",
    deleteConfirm: (name: string) => `確定要刪除模型「${name}」嗎？`,
    modelDeleted: "模型已刪除。",
    deleteFailed: "刪除模型失敗。",
    contextBadge: (thousands: number) => `${thousands}K 上下文`,
    fallbackBadge: (count: number) => `${count} 個降級模型`,
    nameLabel: "名稱",
    interfaceLabel: "介面",
    providerLabel: "提供方",
    customUseLabel: "自訂 use",
    descriptionLabel: "描述",
    thinkingLabel: "思考",
    reasoningLabel: "推理能力",
    visionLabel: "視覺",
    contextWindowLabel: "上下文窗口",
    fallbackChainLabel: "降級鏈路",
    yes: "是",
    no: "否",
  },
};

const taskWorkspaceCopy: Record<Locale, TaskWorkspaceCopy> = {
  "en-US": {
    template: "Template",
    currentPhase: "Current phase",
    missingInputs: "Missing inputs",
    none: "None",
    addGoalForBrain: "Add a task goal to generate Brain contract output.",
    topologyTitle: "Agent Topology",
    topologyDescription: "Agent and runtime layout for this task workspace.",
    taskMode: "Task mode",
    agentCount: "Agent count",
    selectedRuntime: "Selected runtime",
    capabilityAlignmentTitle: "Capability Alignment",
    capabilityAlignmentDescription: "Runtime, system execution, and Brain surfaces aligned to this task.",
    runtimeLabel: "Runtime",
    loadingRuntime: "Loading runtime capabilities…",
    systemExecutionLabel: "System Execution",
    loadingSystemExecution: "Loading system execution capabilities…",
    policySurfaceLabel: "Policy Surface",
    loadingPermissionPolicy: "Loading permission policy…",
    serverCliLabel: "Server CLI",
    serverCliDescription: "Run bounded server-side CLI for quick operator checks without leaving the task workspace.",
    systemCliBlocked: "Current task permission mode does not allow system-scope CLI.",
    policyEnforcedNote: "Policy enforcement still happens on the server.",
    brainCompilationLabel: "Brain Compilation",
    compilingPlan: "Compiling plan…",
    cardDetailsTitle: "Card details",
    cardDetailsDescription: "Inspect the selected workflow card, its bound agent, prompt preview, and archive documents.",
    noCardDescription: "No card description yet.",
    boundAgentLabel: "Bound agent",
    permissionLabel: "Permission",
    agentRoleLabel: "Agent role",
    modelLabel: "Model",
    documentRoleLabel: "Document role",
    canvasPositionLabel: "Canvas position",
    branchTaskLabel: "Branch task",
    promptPreviewLabel: "Prompt preview",
    archiveDocumentsLabel: "Archive documents",
    selectCardHint: "Select a workflow card to inspect its agent binding and archive files.",
  },
  "ja": {
    template: "テンプレート",
    currentPhase: "現在フェーズ",
    missingInputs: "不足入力",
    none: "なし",
    addGoalForBrain: "Brain 合約出力を生成するには、先にタスク目標を追加してください。",
    topologyTitle: "エージェント構成",
    topologyDescription: "このタスクワークスペースのエージェントとランタイム構成です。",
    taskMode: "タスクモード",
    agentCount: "エージェント数",
    selectedRuntime: "選択中ランタイム",
    capabilityAlignmentTitle: "能力对齐",
    capabilityAlignmentDescription: "此任务已对齐运行时、系统执行与 Brain 规划面。",
    runtimeLabel: "运行时",
    loadingRuntime: "正在加载运行时能力…",
    systemExecutionLabel: "系统执行",
    loadingSystemExecution: "正在加载系统执行能力…",
    policySurfaceLabel: "权限面",
    loadingPermissionPolicy: "正在加载权限策略…",
    serverCliLabel: "服务端 CLI",
    serverCliDescription: "无需离开任务工作区，即可运行受限的服务端 CLI 进行快速核查。",
    systemCliBlocked: "当前任务权限模式不允许系统级 CLI。",
    policyEnforcedNote: "服务端仍会继续执行权限校验。",
    brainCompilationLabel: "Brain 编译",
    compilingPlan: "正在编译计划…",
    cardDetailsTitle: "卡片详情",
    cardDetailsDescription: "查看当前工作流卡片、绑定智能体、提示词预览和归档文档。",
    noCardDescription: "当前卡片还没有描述。",
    boundAgentLabel: "绑定智能体",
    permissionLabel: "权限",
    agentRoleLabel: "智能体角色",
    modelLabel: "模型",
    documentRoleLabel: "文档角色",
    canvasPositionLabel: "画布坐标",
    branchTaskLabel: "分支任务",
    promptPreviewLabel: "提示词预览",
    archiveDocumentsLabel: "归档文档",
    selectCardHint: "选择一个工作流卡片以查看绑定关系与归档文件。",
  },
  "ko": {
    template: "템플릿",
    currentPhase: "현재 단계",
    missingInputs: "누락 입력",
    none: "없음",
    addGoalForBrain: "Brain 계약 출력을 생성하려면 먼저 작업 목표를 추가하세요.",
    topologyTitle: "에이전트 토폴로지",
    topologyDescription: "이 작업 워크스페이스의 에이전트 및 런타임 배치입니다.",
    taskMode: "작업 모드",
    agentCount: "에이전트 수",
    selectedRuntime: "선택된 런타임",
    capabilityAlignmentTitle: "能力对齐",
    capabilityAlignmentDescription: "此任务已对齐运行时、系统执行与 Brain 规划面。",
    runtimeLabel: "运行时",
    loadingRuntime: "正在加载运行时能力…",
    systemExecutionLabel: "系统执行",
    loadingSystemExecution: "正在加载系统执行能力…",
    policySurfaceLabel: "权限面",
    loadingPermissionPolicy: "正在加载权限策略…",
    serverCliLabel: "服务端 CLI",
    serverCliDescription: "无需离开任务工作区，即可运行受限的服务端 CLI 进行快速核查。",
    systemCliBlocked: "当前任务权限模式不允许系统级 CLI。",
    policyEnforcedNote: "服务端仍会继续执行权限校验。",
    brainCompilationLabel: "Brain 编译",
    compilingPlan: "正在编译计划…",
    cardDetailsTitle: "卡片详情",
    cardDetailsDescription: "查看当前工作流卡片、绑定智能体、提示词预览和归档文档。",
    noCardDescription: "当前卡片还没有描述。",
    boundAgentLabel: "绑定智能体",
    permissionLabel: "权限",
    agentRoleLabel: "智能体角色",
    modelLabel: "模型",
    documentRoleLabel: "文档角色",
    canvasPositionLabel: "画布坐标",
    branchTaskLabel: "分支任务",
    promptPreviewLabel: "提示词预览",
    archiveDocumentsLabel: "归档文档",
    selectCardHint: "选择一个工作流卡片以查看绑定关系与归档文件。",
  },
  "zh-CN": {
    template: "模板",
    currentPhase: "当前阶段",
    missingInputs: "缺失输入",
    none: "无",
    addGoalForBrain: "请先填写任务目标，再生成 Brain 合约输出。",
    topologyTitle: "智能体拓扑",
    topologyDescription: "当前任务工作区的智能体与运行时布局。",
    taskMode: "任务模式",
    agentCount: "智能体数量",
    selectedRuntime: "已选运行时",
    capabilityAlignmentTitle: "能力对齐",
    capabilityAlignmentDescription: "当前任务已对齐运行时、系统执行和 Brain 规划面。",
    runtimeLabel: "运行时",
    loadingRuntime: "正在加载运行时能力…",
    systemExecutionLabel: "系统执行",
    loadingSystemExecution: "正在加载系统执行能力…",
    policySurfaceLabel: "权限面",
    loadingPermissionPolicy: "正在加载权限策略…",
    serverCliLabel: "服务端 CLI",
    serverCliDescription: "无需离开任务工作区，即可运行受限的服务端 CLI 做快速排查。",
    systemCliBlocked: "当前任务权限模式不允许系统级 CLI。",
    policyEnforcedNote: "服务端仍会继续执行权限校验。",
    brainCompilationLabel: "Brain 编译",
    compilingPlan: "正在编译计划…",
    cardDetailsTitle: "卡片详情",
    cardDetailsDescription: "查看当前工作流卡片、绑定智能体、提示词预览和归档文档。",
    noCardDescription: "当前卡片还没有描述。",
    boundAgentLabel: "绑定智能体",
    permissionLabel: "权限",
    agentRoleLabel: "智能体角色",
    modelLabel: "模型",
    documentRoleLabel: "文档角色",
    canvasPositionLabel: "画布坐标",
    branchTaskLabel: "分支任务",
    promptPreviewLabel: "提示词预览",
    archiveDocumentsLabel: "归档文档",
    selectCardHint: "选择一个工作流卡片，以查看绑定关系和归档文件。",
  },
  "zh-TW": {
    template: "模板",
    currentPhase: "目前階段",
    missingInputs: "缺失輸入",
    none: "無",
    addGoalForBrain: "請先填寫任務目標，再生成 Brain 合約輸出。",
    topologyTitle: "代理拓撲",
    topologyDescription: "目前任務工作區的代理與執行時布局。",
    taskMode: "任務模式",
    agentCount: "代理數量",
    selectedRuntime: "已選執行時",
    capabilityAlignmentTitle: "能力對齊",
    capabilityAlignmentDescription: "目前任務已對齊執行時、系統執行與 Brain 規劃面。",
    runtimeLabel: "執行時",
    loadingRuntime: "正在載入執行時能力…",
    systemExecutionLabel: "系統執行",
    loadingSystemExecution: "正在載入系統執行能力…",
    policySurfaceLabel: "權限面",
    loadingPermissionPolicy: "正在載入權限策略…",
    serverCliLabel: "伺服器 CLI",
    serverCliDescription: "無需離開任務工作區，即可執行受限的伺服器 CLI 做快速排查。",
    systemCliBlocked: "目前任務權限模式不允許系統級 CLI。",
    policyEnforcedNote: "伺服器端仍會繼續執行權限校驗。",
    brainCompilationLabel: "Brain 編譯",
    compilingPlan: "正在編譯計畫…",
    cardDetailsTitle: "卡片詳情",
    cardDetailsDescription: "查看目前工作流卡片、綁定代理、提示詞預覽與歸檔文件。",
    noCardDescription: "目前卡片還沒有描述。",
    boundAgentLabel: "綁定代理",
    permissionLabel: "權限",
    agentRoleLabel: "代理角色",
    modelLabel: "模型",
    documentRoleLabel: "文件角色",
    canvasPositionLabel: "畫布座標",
    branchTaskLabel: "分支任務",
    promptPreviewLabel: "提示詞預覽",
    archiveDocumentsLabel: "歸檔文件",
    selectCardHint: "選擇一個工作流卡片，以查看綁定關係與歸檔文件。",
  },
};

const taskRuntimeCopy: Record<Locale, TaskRuntimeCopy> = {
  "en-US": {
    workflowCompiledTitle: "Workflow compiled",
    workflowCompiledDetail: "Task graph refreshed from the backend planner.",
    workflowStartedTitle: "Workflow started",
    workflowStartedDetail: "Backend task workspace execution was scheduled.",
    workflowPausedTitle: "Workflow paused",
    workflowPausedDetail: "Task workspace execution was paused.",
    workflowResumedTitle: "Workflow resumed",
    workflowResumedDetail: "Task workspace execution resumed.",
    workflowTerminatedTitle: "Workflow terminated",
    workflowTerminatedDetail: "Task workspace execution was terminated.",
    workflowGraphUpdatedTitle: "Workflow graph updated",
    workflowGraphUpdatedDetail: "Card graph changes were sent to the backend task workspace.",
    noWorkflowRuntimeTitle: "No workflow runtime yet",
    noWorkflowRuntimeDescription: "Create a TaskWorkspace from this chat to run the real workflow backend.",
    selectRuntimeTitle: "Select a workflow runtime",
    selectRuntimeDescription: "Choose a TaskWorkspace on the left to inspect or run the real workflow backend.",
    loadingRuntimeTitle: "Loading workflow runtime…",
    loadingRuntimeDescription: "Fetching the live TaskWorkspace state from the backend.",
    noGoalProvided: "No goal provided",
    linkedBadge: "Linked",
    openPage: "Open page",
    modeLabel: "Mode",
    progressLabel: "Progress",
    threadBindingLabel: "Thread binding",
    linkedToThisChat: "Linked to this chat",
    visibleGlobally: "Visible globally",
    agentsTitle: "Agents",
    agentsDescription: "Live runtime agents attached to this workflow.",
    noAgentsRegistered: "No agents registered.",
    checkpointsTitle: "Checkpoints",
    checkpointsDescription: "Latest saved workflow checkpoints.",
    noCheckpoints: "No checkpoints saved yet.",
    realWorkflowRuntimeTitle: "Real workflow runtime",
    realWorkflowRuntimeDescription: "Create or select a backend TaskWorkspace for this chat.",
    workflowNameLabel: "Workflow name",
    goalLabel: "Goal",
    modeSelectLabel: "Mode",
    createFromChatContext: "Create from chat context",
    linkedWorkflowsCount: (count: number) => `${count} workflow(s) already linked to this thread.`,
    noLinkedWorkflows: "No workflow linked to this thread yet. The list below falls back to global workflows.",
  },
  ja: {
    workflowCompiledTitle: "工作流已编译",
    workflowCompiledDetail: "任务图已按后端规划器刷新。",
    workflowStartedTitle: "工作流已启动",
    workflowStartedDetail: "后端任务工作区执行已进入调度。",
    workflowPausedTitle: "工作流已暂停",
    workflowPausedDetail: "任务工作区执行已暂停。",
    workflowResumedTitle: "工作流已恢复",
    workflowResumedDetail: "任务工作区执行已继续。",
    workflowTerminatedTitle: "工作流已终止",
    workflowTerminatedDetail: "任务工作区执行已终止。",
    workflowGraphUpdatedTitle: "工作流画布已更新",
    workflowGraphUpdatedDetail: "卡片图变更已发送到后端任务工作区。",
    noWorkflowRuntimeTitle: "还没有工作流运行时",
    noWorkflowRuntimeDescription: "可从当前对话创建 TaskWorkspace，运行真实后端工作流。",
    selectRuntimeTitle: "选择工作流运行时",
    selectRuntimeDescription: "在左侧选择一个 TaskWorkspace，查看或运行真实后端工作流。",
    loadingRuntimeTitle: "正在加载工作流运行时…",
    loadingRuntimeDescription: "正在从后端拉取实时 TaskWorkspace 状态。",
    noGoalProvided: "暂无任务目标",
    linkedBadge: "已关联",
    openPage: "打开页面",
    modeLabel: "模式",
    progressLabel: "进度",
    threadBindingLabel: "线程绑定",
    linkedToThisChat: "已绑定当前对话",
    visibleGlobally: "全局可见",
    agentsTitle: "智能体",
    agentsDescription: "当前工作流挂载的实时运行时智能体。",
    noAgentsRegistered: "当前没有注册智能体。",
    checkpointsTitle: "检查点",
    checkpointsDescription: "最近保存的工作流检查点。",
    noCheckpoints: "还没有保存检查点。",
    realWorkflowRuntimeTitle: "真实工作流运行时",
    realWorkflowRuntimeDescription: "为当前对话创建或选择一个后端 TaskWorkspace。",
    workflowNameLabel: "工作流名称",
    goalLabel: "目标",
    modeSelectLabel: "模式",
    createFromChatContext: "从对话上下文创建",
    linkedWorkflowsCount: (count: number) => `当前线程已关联 ${count} 个工作流。`,
    noLinkedWorkflows: "当前线程还没有关联工作流，下面列表会回退显示全局工作流。",
  },
  ko: {
    workflowCompiledTitle: "工作流已编译",
    workflowCompiledDetail: "任务图已按后端规划器刷新。",
    workflowStartedTitle: "工作流已启动",
    workflowStartedDetail: "后端任务工作区执行已进入调度。",
    workflowPausedTitle: "工作流已暂停",
    workflowPausedDetail: "任务工作区执行已暂停。",
    workflowResumedTitle: "工作流已恢复",
    workflowResumedDetail: "任务工作区执行已继续。",
    workflowTerminatedTitle: "工作流已终止",
    workflowTerminatedDetail: "任务工作区执行已终止。",
    workflowGraphUpdatedTitle: "工作流画布已更新",
    workflowGraphUpdatedDetail: "卡片图变更已发送到后端任务工作区。",
    noWorkflowRuntimeTitle: "还没有工作流运行时",
    noWorkflowRuntimeDescription: "可从当前对话创建 TaskWorkspace，运行真实后端工作流。",
    selectRuntimeTitle: "选择工作流运行时",
    selectRuntimeDescription: "在左侧选择一个 TaskWorkspace，查看或运行真实后端工作流。",
    loadingRuntimeTitle: "正在加载工作流运行时…",
    loadingRuntimeDescription: "正在从后端拉取实时 TaskWorkspace 状态。",
    noGoalProvided: "暂无任务目标",
    linkedBadge: "已关联",
    openPage: "打开页面",
    modeLabel: "模式",
    progressLabel: "进度",
    threadBindingLabel: "线程绑定",
    linkedToThisChat: "已绑定当前对话",
    visibleGlobally: "全局可见",
    agentsTitle: "智能体",
    agentsDescription: "当前工作流挂载的实时运行时智能体。",
    noAgentsRegistered: "当前没有注册智能体。",
    checkpointsTitle: "检查点",
    checkpointsDescription: "最近保存的工作流检查点。",
    noCheckpoints: "还没有保存检查点。",
    realWorkflowRuntimeTitle: "真实工作流运行时",
    realWorkflowRuntimeDescription: "为当前对话创建或选择一个后端 TaskWorkspace。",
    workflowNameLabel: "工作流名称",
    goalLabel: "目标",
    modeSelectLabel: "模式",
    createFromChatContext: "从对话上下文创建",
    linkedWorkflowsCount: (count: number) => `当前线程已关联 ${count} 个工作流。`,
    noLinkedWorkflows: "当前线程还没有关联工作流，下面列表会回退显示全局工作流。",
  },
  "zh-CN": {
    workflowCompiledTitle: "工作流已编译",
    workflowCompiledDetail: "任务图已按后端规划器刷新。",
    workflowStartedTitle: "工作流已启动",
    workflowStartedDetail: "后端任务工作区执行已进入调度。",
    workflowPausedTitle: "工作流已暂停",
    workflowPausedDetail: "任务工作区执行已暂停。",
    workflowResumedTitle: "工作流已恢复",
    workflowResumedDetail: "任务工作区执行已继续。",
    workflowTerminatedTitle: "工作流已终止",
    workflowTerminatedDetail: "任务工作区执行已终止。",
    workflowGraphUpdatedTitle: "工作流画布已更新",
    workflowGraphUpdatedDetail: "卡片图变更已发送到后端任务工作区。",
    noWorkflowRuntimeTitle: "还没有工作流运行时",
    noWorkflowRuntimeDescription: "可以从当前对话创建 TaskWorkspace，运行真实后端工作流。",
    selectRuntimeTitle: "选择工作流运行时",
    selectRuntimeDescription: "在左侧选择一个 TaskWorkspace，查看或运行真实后端工作流。",
    loadingRuntimeTitle: "正在加载工作流运行时…",
    loadingRuntimeDescription: "正在从后端拉取实时 TaskWorkspace 状态。",
    noGoalProvided: "暂无任务目标",
    linkedBadge: "已关联",
    openPage: "打开页面",
    modeLabel: "模式",
    progressLabel: "进度",
    threadBindingLabel: "线程绑定",
    linkedToThisChat: "已绑定当前对话",
    visibleGlobally: "全局可见",
    agentsTitle: "智能体",
    agentsDescription: "当前工作流挂载的实时运行时智能体。",
    noAgentsRegistered: "当前没有注册智能体。",
    checkpointsTitle: "检查点",
    checkpointsDescription: "最近保存的工作流检查点。",
    noCheckpoints: "还没有保存检查点。",
    realWorkflowRuntimeTitle: "真实工作流运行时",
    realWorkflowRuntimeDescription: "为当前对话创建或选择一个后端 TaskWorkspace。",
    workflowNameLabel: "工作流名称",
    goalLabel: "目标",
    modeSelectLabel: "模式",
    createFromChatContext: "从对话上下文创建",
    linkedWorkflowsCount: (count: number) => `当前线程已关联 ${count} 个工作流。`,
    noLinkedWorkflows: "当前线程还没有关联工作流，下面列表会回退显示全局工作流。",
  },
  "zh-TW": {
    workflowCompiledTitle: "工作流已編譯",
    workflowCompiledDetail: "任務圖已按後端規劃器刷新。",
    workflowStartedTitle: "工作流已啟動",
    workflowStartedDetail: "後端任務工作區執行已進入調度。",
    workflowPausedTitle: "工作流已暫停",
    workflowPausedDetail: "任務工作區執行已暫停。",
    workflowResumedTitle: "工作流已恢復",
    workflowResumedDetail: "任務工作區執行已繼續。",
    workflowTerminatedTitle: "工作流已終止",
    workflowTerminatedDetail: "任務工作區執行已終止。",
    workflowGraphUpdatedTitle: "工作流畫布已更新",
    workflowGraphUpdatedDetail: "卡片圖變更已發送到後端任務工作區。",
    noWorkflowRuntimeTitle: "還沒有工作流執行時",
    noWorkflowRuntimeDescription: "可以從目前對話建立 TaskWorkspace，執行真實後端工作流。",
    selectRuntimeTitle: "選擇工作流執行時",
    selectRuntimeDescription: "在左側選擇一個 TaskWorkspace，查看或執行真實後端工作流。",
    loadingRuntimeTitle: "正在載入工作流執行時…",
    loadingRuntimeDescription: "正在從後端取得即時 TaskWorkspace 狀態。",
    noGoalProvided: "暫無任務目標",
    linkedBadge: "已關聯",
    openPage: "打開頁面",
    modeLabel: "模式",
    progressLabel: "進度",
    threadBindingLabel: "執行緒綁定",
    linkedToThisChat: "已綁定目前對話",
    visibleGlobally: "全域可見",
    agentsTitle: "代理",
    agentsDescription: "目前工作流掛載的即時執行時代理。",
    noAgentsRegistered: "目前沒有註冊代理。",
    checkpointsTitle: "檢查點",
    checkpointsDescription: "最近保存的工作流檢查點。",
    noCheckpoints: "還沒有保存檢查點。",
    realWorkflowRuntimeTitle: "真實工作流執行時",
    realWorkflowRuntimeDescription: "為目前對話建立或選擇一個後端 TaskWorkspace。",
    workflowNameLabel: "工作流名稱",
    goalLabel: "目標",
    modeSelectLabel: "模式",
    createFromChatContext: "從對話上下文建立",
    linkedWorkflowsCount: (count: number) => `目前執行緒已關聯 ${count} 個工作流。`,
    noLinkedWorkflows: "目前執行緒還沒有關聯工作流，下面列表會回退顯示全域工作流。",
  },
};

export function getWorkspaceLocaleCopy(locale: Locale): WorkspaceLocaleCopy {
  return {
    modelFields: modelFields[locale] ?? modelFields["en-US"],
    welcome: welcomeCopy[locale] ?? welcomeCopy["en-US"],
    agentWelcome: agentWelcomeCopy[locale] ?? agentWelcomeCopy["en-US"],
    setupWizard: setupWizardCopy[locale] ?? setupWizardCopy["en-US"],
    modelsPage: modelsPageCopy[locale] ?? modelsPageCopy["en-US"],
    taskWorkspace: taskWorkspaceCopy[locale] ?? taskWorkspaceCopy["en-US"],
    taskRuntime: taskRuntimeCopy[locale] ?? taskRuntimeCopy["en-US"],
  };
}
