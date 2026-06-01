import type { LucideIcon } from "lucide-react";

export interface Translations {
  // Locale meta
  locale: {
    localName: string;
  };

  // Common
  common: {
    home: string;
    settings: string;
    delete: string;
    rename: string;
    share: string;
    openInNewWindow: string;
    close: string;
    more: string;
    search: string;
    download: string;
    thinking: string;
    artifacts: string;
    public: string;
    custom: string;
    notAvailableInDemoMode: string;
    loading: string;
    version: string;
    lastUpdated: string;
    code: string;
    preview: string;
    cancel: string;
    save: string;
    install: string;
    create: string;
    all: string;
    continueTask: string;
    deleteAll: string;
    deleteAllConfirm: string;
    deleteAllSuccess: string;
    deleteConfirm: string;
  };

  // Welcome
  welcome: {
    greeting: string;
    description: string;
    createYourOwnSkill: string;
    createYourOwnSkillDescription: string;
    bootstrapModelReady: string;
    bootstrapModelNotInstalled: string;
    bootstrapRecommendedModel: string;
  };

  // Clipboard
  clipboard: {
    copyToClipboard: string;
    copiedToClipboard: string;
    failedToCopyToClipboard: string;
    linkCopied: string;
  };

  // Input Box
  inputBox: {
    placeholder: string;
    createSkillPrompt: string;
    addAttachments: string;
    voiceStart: string;
    voiceStop: string;
    voiceUnsupported: string;
    agentDefault: string;
    agentLabel: string;
    searchAgents: string;
    mode: string;
    flashMode: string;
    flashModeDescription: string;
    reasoningMode: string;
    reasoningModeDescription: string;
    proMode: string;
    proModeDescription: string;
    ultraMode: string;
    ultraModeDescription: string;
    reasoningEffort: string;
    reasoningEffortMinimal: string;
    reasoningEffortMinimalDescription: string;
    reasoningEffortLow: string;
    reasoningEffortLowDescription: string;
    reasoningEffortMedium: string;
    reasoningEffortMediumDescription: string;
    reasoningEffortHigh: string;
    reasoningEffortHighDescription: string;
    searchModels: string;
    surpriseMe: string;
    surpriseMePrompt: string;
    suggestions: {
      suggestion: string;
      prompt: string;
      icon: LucideIcon;
    }[];
    suggestionsCreate: (
      | {
          suggestion: string;
          prompt: string;
          icon: LucideIcon;
        }
      | {
          type: "separator";
        }
    )[];
  };

  // Sidebar
  sidebar: {
    recentChats: string;
    newChat: string;
    chats: string;
    demoChats: string;
    agents: string;
    tasks: string;
    workflows: string;
    configuration: string;
    skills: string;
    mcp: string;
    models: string;
    evolution: string;
    evolutionDesc: string;
    plugins: string;
    pluginsDesc: string;
    channels: string;
    channelsDesc: string;
    // Evolution page
    evolutionEnabled: string;
    evolutionEnabledDesc: string;
    autoFix: string;
    autoFixDesc: string;
    autoDerive: string;
    autoDeriveDesc: string;
    autoCapture: string;
    autoCaptureDesc: string;
    qualityMonitoring: string;
    qualityMonitoringDesc: string;
    cloudSync: string;
    cloudSyncDesc: string;
    qualityMetrics: string;
    healthCheck: string;
    noMetrics: string;
    noHealth: string;
    applied: string;
    success: string;
    failures: string;
    healthy: string;
    unhealthy: string;
    successRate: string;
    total: string;
    evolutionStartResearch: string;
    evolutionStartResearchDesc: string;
    evolutionStartSuccess: string;
    evolutionStart: string;
    // Plugins page
    allPlugins: string;
    engineering: string;
    review: string;
    runtime: string;
    integration: string;
    noPlugins: string;
  };

  // Agents
  agents: {
    title: string;
    description: string;
    newAgent: string;
    emptyTitle: string;
    emptyDescription: string;
    loadFailedTitle: string;
    loadFailedDescription: string;
    reloadAgents: string;
    chat: string;
    delete: string;
    deleteConfirm: string;
    deleteSuccess: string;
    newChat: string;
    createPageTitle: string;
    createPageSubtitle: string;
    nameStepTitle: string;
    nameStepHint: string;
    nameStepPlaceholder: string;
    nameStepContinue: string;
    nameStepInvalidError: string;
    nameStepAlreadyExistsError: string;
    nameStepCheckError: string;
    nameStepBootstrapMessage: string;
    agentCreated: string;
    startChatting: string;
    backToGallery: string;
    settings: string;
    settingsTitle: string;
    nameLabel: string;
    avatarLabel: string;
    avatarUploading: string;
    avatarClickToChange: string;
    descriptionLabel: string;
    providerLabel: string;
    providerAll: string;
    providerAuto: string;
    modelLabel: string;
    modelNone: string;
    templateLabel: string;
    templateNone: string;
    templateHint: string;
    templateInstallHint: string;
    installAgencyAgents: string;
    installingAgencyAgents: string;
    installAgencyAgentsFailed: string;
    toolGroupsLabel: string;
    toolGroupsHint: string;
    soulLabel: string;
    saveSuccess: string;
  };

  // Workflows
  workflows: {
    title: string;
    description: string;
    newWorkflow: string;
    emptyTitle: string;
    emptyDescription: string;
    loadFailedTitle: string;
    loadFailedDescription: string;
    reloadWorkflows: string;
    modeChat: string;
    modeCron: string;
    modeYolo: string;
    modeChatDesc: string;
    modeCronDesc: string;
    modeYoloDesc: string;
    scheduleHint: string;
    scheduleEmptyRunsNow: string;
    scheduleInvalid: string;
    chain: string;
    branch: string;
    swarm: string;
    editWorkflow: string;
    deleteWorkflow: string;
    deleteConfirm: string;
    saveSuccess: string;
    wizardStepTask: string;
    wizardStepAgent: string;
    wizardStepTopology: string;
    wizardStepExecution: string;
    wizardPrimaryAgent: string;
    wizardAdditionalAgents: string;
    wizardSubAgents: string;
    systemDefault: string;
    taskName: string;
    taskGoal: string;
    singleAgent: string;
    singleAgentDesc: string;
    multiAgent: string;
    multiAgentDesc: string;
    chainDesc: string;
    branchDesc: string;
    swarmDesc: string;
    statusCreated: string;
    statusRunning: string;
    statusPaused: string;
    statusWaitingReview: string;
    statusCompleted: string;
    statusFailed: string;
    statusTerminated: string;
    run: string;
    stop: string;
    pause: string;
    resume: string;
    back: string;
    create: string;
    colProject: string;
    colStatus: string;
    colProgress: string;
    colRuntime: string;
    colRunMode: string;
    colUpdated: string;
    colActions: string;
    activeShort: string;
    noGoal: string;
    resultTitle: string;
    resultContent: string;
    generatedFiles: string;
    resultDocumentSource: string;
    resultSections: string;
    noResultSections: string;
    copyResult: string;
    downloadResult: string;
    langgraphTopologyLabel: string;
    executionLogsTitle: string;
    executionLogsDescription: string;
    noExecutionLogs: string;
    noResultYet: string;
    failureAnalysis: string;
    failureReason: string;
    failureOutput: string;
    possibleSolutions: string;
    solutionCheckLog: string;
    solutionCheckConfig: string;
    solutionRetry: string;
  };

  // Setup Wizard
  setupWizard: {
    title: string;
    subtitle: string;
    stepWorkspace: string;
    stepWorkspaceDesc: string;
    stepWorkspaceHint: string;
    stepModel: string;
    stepModelDesc: string;
    stepModelHint: string;
    stepSandbox: string;
    stepSandboxDesc: string;
    sandboxLocal: string;
    sandboxLocalDesc: string;
    sandboxDocker: string;
    sandboxDockerDesc: string;
    complete: string;
    completeDesc: string;
    next: string;
    skip: string;
    finish: string;
    validating: string;
    pathValid: string;
    willBeCreated: string;
    freeSpace: string;
    serverError: string;
    currentBackendPath: string;
    modelsReady: string;
    skillsAvailable: string;
    noModelsYet: string;
    applying: string;
    browse: string;
    selectFolder: string;
    goUp: string;
    newFolder: string;
    emptyDir: string;
    confirmSelect: string;
    newFolderName: string;
    createFolderError: string;
    networkError: string;
  };

  // Breadcrumb
  breadcrumb: {
    workspace: string;
    chats: string;
    tasks: string;
  };

  // Workspace
  workspace: {
    officialWebsite: string;
    githubTooltip: string;
    settingsAndMore: string;
    visitGithub: string;
    reportIssue: string;
    contactUs: string;
    about: string;
    inspector: {
      title: string;
      parallelSummary: (branches: number, agents: number) => string;
      resetView: string;
      board: string;
      canvas: string;
      executionConsole: string;
      collapse: string;
      expand: string;
      attention: string;
      active: string;
      info: string;
      noArtifactsYet: string;
      noArtifactsDescription: string;
      thinkingTab: string;
      terminalTab: string;
      eventsTab: string;
      reasoningVisibility: string;
      hidden: string;
      enabled: string;
      thinkingFlashDescription: string;
      thinkingEnabledDescription: string;
      streamingDescription: string;
      idleDescription: string;
      noCommandActivityYet: string;
      noCommandActivityDescription: string;
      terminalHeadline: string;
      terminalDescription: string;
      terminalScope: string;
      workspaceScope: string;
      systemScope: string;
      terminalReady: string;
      terminalUnavailable: string;
      commandLabel: string;
      commandPlaceholder: string;
      noteLabel: string;
      notePlaceholder: string;
      taskFilterLabel: string;
      allTasks: string;
      sessionLookupLabel: string;
      sessionLookupPlaceholder: string;
      sessionLookupButton: string;
      sessionLookupRequired: string;
      sessionLookupNotFound: string;
      sessionLookupFailed: string;
      terminalRunHint: string;
      runCommand: string;
      runningCommand: string;
      terminalRequestFailed: string;
      latestSession: string;
      latestOutput: string;
      recentSessions: string;
      liveSync: string;
      refreshSession: string;
      loadingTerminalOutput: string;
      lastUpdated: string;
      exitCode: string;
      blockedReason: string;
      completedSteps: string;
      pendingSteps: string;
      recoveryAvailable: string;
      recentCommands: string;
      auditTrail: string;
      noTerminalOutputYet: string;
      noTerminalOutputDescription: string;
      noTerminalAuditYet: string;
      noRuntimeEventsYet: string;
      noRuntimeEventsDescription: string;
      runtimeEvent: string;
      returnedToMainAgent: string;
      stepFailed: string;
      stillRunning: string;
      primaryModel: string;
      fallbackChain: string;
      continuation: string;
      workflowState: string;
      agentBudget: string;
      agentBudgetValue: (
        maxActivePerThread: number,
        maxTotalPerThread: number,
        maxConcurrentGlobal: number,
      ) => string;
      memoryGuard: string;
      unavailable: string;
      noFallbackChain: string;
      freshThread: string;
      noSavedWorkflow: string;
      workflowResumed: (count: number) => string;
      workflowLoaded: (count: number) => string;
      continuationLoadedTitle: string;
      continuationLoadedDetail: (source: string) => string;
      workflowRestoredTitle: string;
      workflowRestoredDetail: (count: number) => string;
      fallbackReadyTitle: string;
      fallbackReadyDetail: (model: string, chain: string) => string;
      memoryGuardTightTitle: string;
      memoryGuardTightDetail: string;
      memoryGuardTruncated: string;
      memoryGuardTruncatedTitle: string;
      memoryGuardTruncatedDetail: string;
      embeddedBackupOnlyTitle: string;
      embeddedBackupOnlyDetail: string;
    };
  };

  // Conversation
  conversation: {
    noMessages: string;
    startConversation: string;
  };

  // Chats
  chats: {
    searchChats: string;
    continueFromHere: string;
  };

  // Page titles (document title)
  pages: {
    appName: string;
    chats: string;
    newChat: string;
    untitled: string;
  };

  // Tool calls
  toolCalls: {
    moreSteps: (count: number) => string;
    lessSteps: string;
    executeCommand: string;
    presentFiles: string;
    needYourHelp: string;
    useTool: (toolName: string) => string;
    searchForRelatedInfo: string;
    searchForRelatedImages: string;
    searchFor: (query: string) => string;
    searchForRelatedImagesFor: (query: string) => string;
    searchOnWebFor: (query: string) => string;
    viewWebPage: string;
    listFolder: string;
    readFile: string;
    writeFile: string;
    clickToViewContent: string;
    writeTodos: string;
    skillInstallTooltip: string;
  };

  softwareInterfaces: {
    title: string;
    description: string;
    refresh: string;
    runtimeTitle: string;
    runtimeDescription: string;
    running: string;
    stopped: string;
    liveGateway: string;
    notConfigured: string;
    notConfiguredDescription: string;
    catalogTitle: string;
    catalogDescription: string;
    all: string;
    totalCount: (count: number) => string;
    messagingCount: (count: number) => string;
    integrationSource: string;
    native: string;
    unknown: string;
    oauthManaged: string;
    connect: string;
    manage: string;
    edit: string;
    logout: string;
    retry: string;
    restart: string;
    saveScopes: string;
    connections: string;
    noConnections: string;
    extraParams: string;
    scopePreferences: string;
    actions: string;
    noActions: string;
    noDescription: string;
    empty: string;
    channelDescription: string;
    identityAware: string;
    configOnly: string;
    replyRelayReady: string;
    replyRelayMissing: string;
    catalogLoadFailed: string;
    manageLoadFailed: string;
    saveFailed: string;
    restartFailed: string;
    switchFailed: string;
    logoutFailed: string;
    logoutSucceeded: string;
    invalidJson: string;
    oauthOpened: string;
    authorizeStarted: string;
    authorizeFailed: string;
    scopesSaved: string;
    scopesSaveFailed: string;
    noEditableFields: string;
    editDescription: string;
    manageDescription: string;
    editTitle: (name: string) => string;
    manageTitle: (name: string) => string;
    manageAria: (name: string) => string;
    editAria: (name: string) => string;
    logoutAria: (name: string) => string;
    logoutConfirm: (name: string) => string;
    requestFailed: (status: number) => string;
    loggedInAs: (name: string, id?: number) => string;
    channelStatus: { healthy: string; degraded: string; stopped: string };
    connectionState: {
      connected: string;
      pending: string;
      expired: string;
      error: string;
      disconnected: string;
    };
    categories: {
      communication: string;
      office: string;
      mail_calendar: string;
      docs_storage: string;
      project_management: string;
      development: string;
      crm_sales: string;
      commerce_payments: string;
      social_media: string;
      automation: string;
    };
    scopes: { read: string; write: string; admin: string };
    scopeDescriptions: { read: string; write: string; admin: string };
    qrUnavailable: string;
    networkError: string;
    channelLoginSucceeded: string;
    channelLoginStatus: string;
    qrLogin: string;
    channelLoggedIn: string;
    qrLoginDescription: string;
    unknownUser: string;
    fetchingQr: string;
    qrAlt: string;
    refreshQr: string;
    configPath: string;
    handler: string;
    ingestPath: string;
    upstreamBridge: string;
    outboundRelay: string;
    configured: string;
  };

  // Uploads
  uploads: {
    uploading: string;
    uploadingFiles: string;
  };

  // Subtasks
  subtasks: {
    subtask: string;
    executing: (count: number) => string;
    in_progress: string;
    completed: string;
    failed: string;
  };

  // Settings
  settings: {
    title: string;
    description: string;
    sections: {
      overview: string;
      appearance: string;
      bootstrap: string;
      evolution: string;
      systemGuard: string;
      systemExecution: string;
      rag: string;
      memory: string;
      tools: string;
      mcp: string;
      hooks: string;
      plugins: string;
      models: string;
      channels: string;
      skills: string;
      notification: string;
      update: string;
      about: string;
    };
    system: {
      title: string;
      description: string;
      runtimeOverview: string;
      repoOverview: string;
      registryTitle: string;
      registryDescription: string;
      compatPreviewTitle: string;
      compatPreviewDescription: string;
      sourceInventory: string;
      installedInventory: string;
      matchedInventory: string;
      refresh: string;
      migrateAll: string;
      migrating: string;
      noResults: string;
      lastRun: string;
      sourceUnavailable: string;
      capabilityRuntime: string;
      capabilityAudit: string;
      cacheWarm: string;
      cacheCold: string;
      listenersActive: string;
      lastInventoryBuild: string;
      lastMigrationAt: string;
      auditTrail: string;
      noAuditEntries: string;
      registryEmpty: string;
      compatSourceUnavailable: string;
      compatImportLabel: string;
      compatImportEnabled: string;
      compatImportDisabled: string;
      trustLevelLabel: string;
      trustTrusted: string;
      trustUntrusted: string;
      conflictsLabel: string;
      blockedItemsLabel: string;
      sourcePathLabel: string;
      linkedSkillsLabel: string;
      configuredOn: string;
      configuredOff: string;
      effectiveOn: string;
      effectiveOff: string;
      activationBlocked: string;
      blockedByTrust: string;
      blockedByConflict: string;
      toggleSupported: string;
      toggleUnsupported: string;
      toggleFailed: string;
      kindSkill: string;
      kindPlugin: string;
      kindMcpServer: string;
      kindHook: string;
      kindCommand: string;
      kindAgentPersona: string;
      kindReference: string;
    };
    memory: {
      title: string;
      description: string;
      empty: string;
      rawJson: string;
      markdown: {
        overview: string;
        userContext: string;
        work: string;
        personal: string;
        topOfMind: string;
        historyBackground: string;
        recentMonths: string;
        earlierContext: string;
        longTermBackground: string;
        updatedAt: string;
        facts: string;
        empty: string;
        table: {
          category: string;
          confidence: string;
          confidenceLevel: {
            veryHigh: string;
            high: string;
            normal: string;
            unknown: string;
          };
          content: string;
          source: string;
          createdAt: string;
          view: string;
        };
      };
    };
    globalMemory: {
      title: string;
      description: string;
      empty: string;
      addEntry: string;
      editEntry: string;
      deleteEntry: string;
      deleteConfirm: string;
      importFile: string;
      importSuccess: string;
      titlePlaceholder: string;
      contentPlaceholder: string;
      save: string;
      cancel: string;
      source: string;
      updatedAt: string;
      unsupportedFormat: string;
    };
    appearance: {
      themeTitle: string;
      themeDescription: string;
      system: string;
      light: string;
      dark: string;
      systemDescription: string;
      lightDescription: string;
      darkDescription: string;
      languageTitle: string;
      languageDescription: string;
    };
    tools: {
      title: string;
      description: string;
    };
    hooks: {
      title: string;
      description: string;
      emptyTitle: string;
      emptyDescription: string;
    };
    skills: {
      title: string;
      description: string;
      createSkill: string;
      installAgencyAgents: string;
      installingAgencyAgents: string;
      emptyTitle: string;
      emptyDescription: string;
      emptyButton: string;
    };
    notification: {
      title: string;
      description: string;
      requestPermission: string;
      deniedHint: string;
      testButton: string;
      testTitle: string;
      testBody: string;
      notSupported: string;
      disableNotification: string;
    };
    acknowledge: {
      emptyTitle: string;
      emptyDescription: string;
    };
    bootstrap: {
      title: string;
      description: string;
      recommendedRuntime: string;
      modelStatus: string;
      installed: string;
      notInstalled: string;
      installing: string;
      installModel: string;
      semanticStore: string;
      vectorDb: string;
      embeddingsShared: string;
      embeddingsDisabled: string;
      indexedCorpusFiles: string;
      onboardingGuide: string;
      generating: string;
      generateGuide: string;
      starterPrompts: string;
      installHint: string;
      indexedLocalDocs: string;
    };
    systemGuard: {
      title: string;
      description: string;
      unavailable: string;
      unavailableDesc: string;
      lifecycleActive: string;
      latestSnapshot: string;
      noSnapshot: string;
      created: string;
      session: string;
      issues: string;
      unavailableValue: string;
      running: string;
      advisory: string;
      repair: string;
      export: string;
      exporting: string;
      latestIssues: string;
      autoRepairable: string;
      noIssueMessage: string;
      retentionTelemetry: string;
      loaded: string;
      namespace: string;
      snapshotCount: string;
      retentionLimit: string;
      unbounded: string;
      retentionHelpText: string;
      recentSnapshots: string;
      refresh: string;
      metadata: string;
      state: string;
      noSnapshotsYet: string;
      latestRepairResult: string;
      outcome: string;
      persistedPhase: string;
      builtinActions: string;
      ok: string;
      attentionRequired: string;
      noBuiltinActions: string;
      advisoryGenerated: string;
      repairFinished: string;
      repairWithIssues: string;
      exportDownloaded: string;
    };
    systemExecution: {
      title: string;
      description: string;
      unavailable: string;
      unavailableDesc: string;
      currentCapability: string;
      enabled: string;
      disabled: string;
      desktopControl: string;
      windowIntrospection: string;
      fileHandoff: string;
      browserHandoff: string;
      yes: string;
      no: string;
      dryRunPlanner: string;
      dryRunPlannerDesc: string;
      goal: string;
      goalPlaceholder: string;
      target: string;
      allowedApps: string;
      allowedAppsPlaceholder: string;
      expectedOutcome: string;
      expectedOutcomePlaceholder: string;
      planning: string;
      generatePlan: string;
      creating: string;
      createSession: string;
      planningFailed: string;
      latestPlan: string;
      missing: string;
      latestSession: string;
      snapshot: string;
      activeApp: string;
      activeWindow: string;
      focusedTarget: string;
      timestamp: string;
      auditLog: string;
      noAuditEntries: string;
    };
    update: {
      title: string;
      checkNow: string;
      currentVersion: string;
      latestVersion: string;
      applyUpdate: string;
      upToDate: string;
      noUpdateDialogTitle: string;
      noUpdateDialogDescription: (version: string) => string;
      confirmUpdateDialogTitle: string;
      confirmUpdateDialogDescription: (version: string) => string;
      updatingStatus: string;
      autoUpdate: string;
      autoUpdateLabel: string;
      autoUpdateDesc: string;
      lastCheck: string;
    };
  };

  // SystemEvents
  systemEvents: {
    title: string;
    clear: string;
    empty: string;
    description: string;
    runtimeAlerts: string;
    threadLoadFailed: string;
    autoContinueResume: string;
    userAborted: string;
  };

  // PermissionMode
  permissionMode: {
    approval: string;
    approvalDescription: string;
    directory: string;
    directoryDescription: string;
    system: string;
    systemDescription: string;
    label: string;
    conversationContext: string;
  };

  // Messages
  messages: {
    showEarlierMessages: string;
  };

  // TaskGraph
  taskGraph: {
    primaryAgent: string;
    subAgent: string;
    doubleClickToEdit: string;
  };

  // ChatLoading
  chatLoading: {
    title: string;
    preparing: string;
    inspectorLoading: string;
  };

  // RagSettings
  ragSettings: {
    sectionTitle: string;
    sectionDescription: string;
    sectionFullDescription: string;
    loadFailed: string;
    unknownError: string;
    savedToast: string;
    downloadStart: string;
    downloadDone: string;
    embeddingTitle: string;
    modelLabel: string;
    cached: string;
    notDownloaded: string;
    redownload: string;
    download: string;
    rerankerTitle: string;
    rerankerEnable: string;
    rerankerHint: string;
    rerankerModel: string;
    paramsTitle: string;
    defaultTopK: string;
    configLocation: string;
    reset: string;
    saving: string;
    save: string;
    modelLabelMiniLM: string;
    modelLabelBgeSmallZh: string;
    modelLabelBgeM3: string;
  };

  // TaskCardDetails
  taskCardDetails: {
    resultDocument: string;
    failureAnalysis: string;
    loadCardDocFailed: string;
    cardDocumentPreview: string;
    openDocument: string;
    noBoundDocument: string;
    loadingCardDoc: string;
    cardDocEmpty: string;
    noDownloadableResult: string;
  };

  // ThreadEvents
  threadEvents: {
    recursionLimit: string;
    contextHandoffSubmitted: string;
    autoContinueAction: string;
    contextLimitHandoff: string;
    incompleteRetryWithReason: string;
    incompleteRetry: string;
    watchdogLongRun: string;
    sessionRefreshed: string;
  };

  // Register
  register: {
    authSuccess: string;
    enterUsername: string;
    needEmailVerify: string;
    loginFailed: string;
    codeSentEmail: string;
    codeWrittenLog: string;
    registerFailed: string;
    deviceVerifyFailed: string;
    codeCheckFailed: string;
    title: string;
    subtitleMail: string;
    subtitleFirst: string;
    subtitleTrust: string;
    tabLogin: string;
    tabRegister: string;
    username: string;
    password: string;
    processing: string;
    userPassLogin: string;
    terminalLogin: string;
    switchTerminal: string;
    email: string;
    displayName: string;
    sending: string;
    sendCode: string;
    enter8Digit: string;
    verifyCode: string;
    devCode: string;
    verifying: string;
    verifyAndEnter: string;
  };
}
