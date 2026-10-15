export type Language = 'en'

export const translations = {
  en: {
    // Header
    appTitle: 'AlgoBots',
    subtitle: 'Multi-AI Model Trading Platform',
    aiTraders: 'AI Traders',
    details: 'Details',
    tradingPanel: 'Trading Panel',
    competition: 'Competition',
    running: 'RUNNING',
    stopped: 'STOPPED',
    adminMode: 'Admin Mode',
    logout: 'Logout',
    switchTrader: 'Switch Trader:',
    view: 'View',

    // Navigation
    realtimeNav: 'Leaderboard',
    configNav: 'Config',
    dashboardNav: 'Dashboard',
    strategyNav: 'Strategy',
    faqNav: 'FAQ',

    // Footer
    footerTitle: 'AlgoBots - AI Trading System',
    footerWarning: '⚠️ Trading involves risk. Use at your own discretion.',

    // Stats Cards
    totalEquity: 'Total Equity',
    availableBalance: 'Available Balance',
    totalPnL: 'Total P&L',
    positions: 'Positions',
    margin: 'Margin',
    free: 'Free',

    // Positions Table
    currentPositions: 'Current Positions',
    active: 'Active',
    symbol: 'Symbol',
    side: 'Side',
    entryPrice: 'Entry Price',
    stopLoss: 'Stop Loss',
    takeProfit: 'Take Profit',
    riskReward: 'Risk/Reward',
    markPrice: 'Mark Price',
    quantity: 'Quantity',
    positionValue: 'Position Value',
    leverage: 'Leverage',
    unrealizedPnL: 'Unrealized P&L',
    liqPrice: 'Liq. Price',
    long: 'LONG',
    short: 'SHORT',
    noPositions: 'No Positions',
    noActivePositions: 'No active trading positions',

    // Recent Decisions
    recentDecisions: 'Recent Decisions',
    lastCycles: 'Last {count} trading cycles',
    noDecisionsYet: 'No Decisions Yet',
    aiDecisionsWillAppear: 'AI trading decisions will appear here',
    cycle: 'Cycle',
    success: 'Success',
    failed: 'Failed',
    inputPrompt: 'Input Prompt',
    aiThinking: 'AI Chain of Thought',
    collapse: 'Collapse',
    expand: 'Expand',

    // Equity Chart
    accountEquityCurve: 'Account Equity Curve',
    noHistoricalData: 'No Historical Data',
    dataWillAppear: 'Equity curve will appear after running a few cycles',
    initialBalance: 'Initial Balance',
    currentEquity: 'Current Equity',
    historicalCycles: 'Historical Cycles',
    displayRange: 'Display Range',
    recent: 'Recent',
    allData: 'All Data',
    cycles: 'Cycles',

    // Comparison Chart
    comparisonMode: 'Comparison Mode',
    dataPoints: 'Data Points',
    currentGap: 'Current Gap',
    count: '{count} pts',

    // TradingView Chart
    marketChart: 'Market Chart',
    viewChart: 'Click to view chart',
    enterSymbol: 'Enter symbol...',
    popularSymbols: 'Popular Symbols',
    fullscreen: 'Fullscreen',
    exitFullscreen: 'Exit Fullscreen',

    // Competition Page
    aiCompetition: 'AI Competition',
    traders: 'traders',
    liveBattle: 'Live Battle',
    realTimeBattle: 'Real-time Battle',
    leader: 'Leader',
    leaderboard: 'Leaderboard',
    live: 'LIVE',
    realTime: 'LIVE',
    performanceComparison: 'Performance Comparison',
    realTimePnL: 'Real-time PnL %',
    realTimePnLPercent: 'Real-time PnL %',
    headToHead: 'Head-to-Head Battle',
    leadingBy: 'Leading by {gap}%',
    behindBy: 'Behind by {gap}%',
    equity: 'Equity',
    pnl: 'P&L',
    pos: 'Pos',

    // AI Traders Management
    manageAITraders: 'Manage your AI trading bots',
    aiModels: 'AI Models',
    exchanges: 'Exchanges',
    createTrader: 'Create Trader',
    modelConfiguration: 'Model Configuration',
    configured: 'Configured',
    notConfigured: 'Not Configured',
    currentTraders: 'Current Traders',
    noTraders: 'No AI Traders',
    createFirstTrader: 'Create your first AI trader to get started',
    dashboardEmptyTitle: "Let's Get Started!",
    dashboardEmptyDescription:
      'Create your first AI trader to automate your trading strategy. Connect an exchange, choose an AI model, and start trading in minutes!',
    goToTradersPage: 'Create Your First Trader',
    configureModelsFirst: 'Please configure AI models first',
    configureExchangesFirst: 'Please configure exchanges first',
    configureModelsAndExchangesFirst:
      'Please configure AI models and exchanges first',
    modelNotConfigured: 'Selected model is not configured',
    exchangeNotConfigured: 'Selected exchange is not configured',
    confirmDeleteTrader: 'Are you sure you want to delete this trader?',
    status: 'Status',
    start: 'Start',
    stop: 'Stop',
    createNewTrader: 'Create New AI Trader',
    selectAIModel: 'Select AI Model',
    selectExchange: 'Select Exchange',
    traderName: 'Trader Name',
    enterTraderName: 'Enter trader name',
    cancel: 'Cancel',
    create: 'Create',
    configureAIModels: 'Configure AI Models',
    configureExchanges: 'Configure Exchanges',
    aiScanInterval: 'AI Scan Decision Interval (minutes)',
    scanIntervalRecommend: 'Recommended: 15-30 minutes',
    useTestnet: 'Use Testnet',
    enabled: 'Enabled',
    save: 'Save',

    // TraderConfigModal - New keys for hardcoded Chinese strings
    fetchBalanceEditModeOnly: 'Only can fetch current balance in edit mode',
    balanceFetched: 'Current balance fetched',
    balanceFetchFailed: 'Failed to fetch balance',
    balanceFetchNetworkError:
      'Failed to fetch balance, please check network connection',
    saving: 'Saving...',
    saveSuccess: 'Saved successfully',
    saveFailed: 'Save failed',
    editTraderConfig: 'Edit Trader Configuration',
    selectStrategyAndConfigParams:
      'Select Strategy and Configure Basic Parameters',
    basicConfig: 'Basic Configuration',
    traderNameRequired: 'Trader Name *',
    enterTraderNamePlaceholder: 'Enter trader name',
    aiModelRequired: 'AI Model *',
    exchangeRequired: 'Exchange *',
    noExchangeAccount: "Don't have an exchange account? Click to register",
    discount: 'Discount',
    selectTradingStrategy: 'Select Trading Strategy',
    useStrategy: 'Use Strategy',
    noStrategyManual: '-- No Strategy (Manual Configuration) --',
    strategyActive: ' (Active)',
    strategyDefault: ' [Default]',
    noStrategyHint: 'No strategies yet, please create in Strategy Studio first',
    strategyDetails: 'Strategy Details',
    activating: 'Activating',
    coinSource: 'Coin Source',
    marginLimit: 'Margin Limit',
    tradingParams: 'Trading Parameters',
    marginMode: 'Margin Mode',
    crossMargin: 'Cross Margin',
    isolatedMargin: 'Isolated Margin',
    competitionDisplay: 'Show in Competition',
    show: 'Show',
    hide: 'Hide',
    hiddenInCompetition:
      'This trader will not be shown in the competition page when hidden',
    initialBalanceLabel: 'Initial Balance ($)',
    fetching: 'Fetching...',
    fetchCurrentBalance: 'Fetch Current Balance',
    balanceUpdateHint:
      'Used to manually update the initial balance baseline (e.g., after deposit/withdrawal)',
    autoFetchBalanceInfo:
      'The system will automatically fetch your account equity as the initial balance',
    fetchingBalance: 'Fetching balance...',
    editTrader: 'Save Changes',
    createTraderButton: 'Create Trader',

    // AI Model Configuration
    officialAPI: 'Official API',
    customAPI: 'Custom API',
    apiKey: 'API Key',
    customAPIURL: 'Custom API URL',
    enterAPIKey: 'Enter API Key',
    enterCustomAPIURL: 'Enter custom API endpoint URL',
    useOfficialAPI: 'Use official API service',
    useCustomAPI: 'Use custom API endpoint',

    // Exchange Configuration
    secretKey: 'Secret Key',
    privateKey: 'Private Key',
    walletAddress: 'Wallet Address',
    user: 'User',
    signer: 'Signer',
    passphrase: 'Passphrase',
    enterPrivateKey: 'Enter Private Key',
    enterWalletAddress: 'Enter Wallet Address',
    enterUser: 'Enter User',
    enterSigner: 'Enter Signer Address',
    enterSecretKey: 'Enter Secret Key',
    enterPassphrase: 'Enter Passphrase',
    hyperliquidPrivateKeyDesc:
      'Hyperliquid uses private key for trading authentication',
    hyperliquidWalletAddressDesc:
      'Wallet address corresponding to the private key',
    // Hyperliquid Agent Wallet (New Security Model)
    hyperliquidAgentWalletTitle: 'Hyperliquid Agent Wallet Configuration',
    hyperliquidAgentWalletDesc:
      'Use Agent Wallet for secure trading: Agent wallet signs transactions (balance ~0), Main wallet holds funds (never expose private key)',
    hyperliquidAgentPrivateKey: 'Agent Private Key',
    enterHyperliquidAgentPrivateKey: 'Enter Agent wallet private key',
    hyperliquidAgentPrivateKeyDesc:
      'Agent wallet private key for signing transactions (keep balance near 0 for security)',
    hyperliquidMainWalletAddress: 'Main Wallet Address',
    enterHyperliquidMainWalletAddress: 'Enter Main wallet address',
    hyperliquidMainWalletAddressDesc:
      'Main wallet address that holds your trading funds (never expose its private key)',
    // Aster API Pro Configuration
    asterApiProTitle: 'Aster API Pro Wallet Configuration',
    asterApiProDesc:
      'Use API Pro wallet for secure trading: API wallet signs transactions, main wallet holds funds (never expose main wallet private key)',
    asterUserDesc:
      'Main wallet address - The EVM wallet address you use to log in to Aster (Note: Only EVM wallets are supported)',
    asterSignerDesc:
      'API Pro wallet address (0x...) - Generate from https://www.asterdex.com/en/api-wallet',
    asterPrivateKeyDesc:
      'API Pro wallet private key - Get from https://www.asterdex.com/en/api-wallet (only used locally for signing, never transmitted)',
    asterUsdtWarning:
      'Important: Aster only tracks USDT balance. Please ensure you use USDT as margin currency to avoid P&L calculation errors caused by price fluctuations of other assets (BNB, ETH, etc.)',
    asterUserLabel: 'Main Wallet Address',
    asterSignerLabel: 'API Pro Wallet Address',
    asterPrivateKeyLabel: 'API Pro Wallet Private Key',
    enterAsterUser: 'Enter main wallet address (0x...)',
    enterAsterSigner: 'Enter API Pro wallet address (0x...)',
    enterAsterPrivateKey: 'Enter API Pro wallet private key',

    // LIGHTER Configuration
    lighterWalletAddress: 'L1 Wallet Address',
    lighterPrivateKey: 'L1 Private Key',
    lighterApiKeyPrivateKey: 'API Key Private Key',
    enterLighterWalletAddress: 'Enter Ethereum wallet address (0x...)',
    enterLighterPrivateKey: 'Enter L1 private key (32 bytes)',
    enterLighterApiKeyPrivateKey:
      'Enter API Key private key (40 bytes, optional)',
    lighterWalletAddressDesc:
      'Your Ethereum wallet address for account identification',
    lighterPrivateKeyDesc:
      'L1 private key for account identification (32-byte ECDSA key)',
    lighterApiKeyPrivateKeyDesc:
      'API Key private key for transaction signing (40-byte Poseidon2 key)',
    lighterApiKeyOptionalNote:
      'Without API Key, system will use limited V1 mode',
    lighterV1Description:
      'Basic Mode - Limited functionality, testing framework only',
    lighterV2Description:
      'Full Mode - Supports Poseidon2 signing and real trading',
    lighterPrivateKeyImported: 'LIGHTER private key imported',

    // Exchange names
    hyperliquidExchangeName: 'Hyperliquid',
    asterExchangeName: 'Aster DEX',

    // Secure input
    secureInputButton: 'Secure Input',
    secureInputReenter: 'Re-enter Securely',
    secureInputClear: 'Clear',
    secureInputHint:
      'Captured via secure two-step input. Use "Re-enter Securely" to update this value.',

    // Two Stage Key Modal
    twoStageModalTitle: 'Secure Key Input',
    twoStageModalDescription:
      'Use a two-step flow to enter your {length}-character private key safely.',
    twoStageStage1Title: 'Step 1 · Enter the first half',
    twoStageStage1Placeholder: 'First 32 characters (include 0x if present)',
    twoStageStage1Hint:
      'Continuing copies an obfuscation string to your clipboard as a diversion.',
    twoStageStage1Error: 'Please enter the first part before continuing.',
    twoStageNext: 'Next',
    twoStageProcessing: 'Processing…',
    twoStageCancel: 'Cancel',
    twoStageStage2Title: 'Step 2 · Enter the rest',
    twoStageStage2Placeholder: 'Remaining characters of your private key',
    twoStageStage2Hint:
      'Paste the obfuscation string somewhere neutral, then finish entering your key.',
    twoStageClipboardSuccess:
      'Obfuscation string copied. Paste it into any text field once before completing.',
    twoStageClipboardReminder:
      'Remember to paste the obfuscation string before submitting to avoid clipboard leaks.',
    twoStageClipboardManual:
      'Automatic copy failed. Copy the obfuscation string below manually.',
    twoStageBack: 'Back',
    twoStageSubmit: 'Confirm',
    twoStageInvalidFormat:
      'Invalid private key format. Expected {length} hexadecimal characters (optional 0x prefix).',
    testnetDescription:
      'Enable to connect to exchange test environment for simulated trading',
    securityWarning: 'Security Warning',
    saveConfiguration: 'Save Configuration',

    // Trader Configuration
    positionMode: 'Position Mode',
    crossMarginMode: 'Cross Margin',
    isolatedMarginMode: 'Isolated Margin',
    crossMarginDescription:
      'Cross margin: All positions share account balance as collateral',
    isolatedMarginDescription:
      'Isolated margin: Each position manages collateral independently, risk isolation',
    leverageConfiguration: 'Leverage Configuration',
    btcEthLeverage: 'BTC/ETH Leverage',
    altcoinLeverage: 'Altcoin Leverage',
    leverageRecommendation:
      'Recommended: BTC/ETH 5-10x, Altcoins 3-5x for risk control',
    tradingSymbols: 'Trading Symbols',
    tradingSymbolsPlaceholder:
      'Enter symbols, comma separated (e.g., BTCUSDT,ETHUSDT,SOLUSDT)',
    selectSymbols: 'Select Symbols',
    selectTradingSymbols: 'Select Trading Symbols',
    selectedSymbolsCount: 'Selected {count} symbols',
    clearSelection: 'Clear All',
    confirmSelection: 'Confirm',
    tradingSymbolsDescription:
      'Empty = use default symbols. Use USDT perps (e.g., BTCUSDT, ETHUSDT) or Hyperliquid XYZ USDC markets (e.g., TSLA-USDC)',
    btcEthLeverageValidation: 'BTC/ETH leverage must be between 1-50x',
    altcoinLeverageValidation: 'Altcoin leverage must be between 1-20x',
    invalidSymbolFormat:
      'Invalid symbol format: {symbol}, use USDT perps or SYMBOL-USDC',

    // System Prompt Templates
    systemPromptTemplate: 'System Prompt Template',
    promptTemplateDefault: 'Default Stable',
    promptTemplateAdaptive: 'Conservative Strategy',
    promptTemplateAdaptiveRelaxed: 'Aggressive Strategy',
    promptTemplateHansen: 'Hansen Strategy',
    promptTemplateNof1: 'NoF1 English Framework',
    promptTemplateTaroLong: 'Taro Long Position',
    promptDescDefault: '📊 Default Stable Strategy',
    promptDescDefaultContent:
      'Maximize Sharpe ratio, balanced risk-reward, suitable for beginners and stable long-term trading',
    promptDescAdaptive: '🛡️ Conservative Strategy (v6.0.0)',
    promptDescAdaptiveContent:
      'Strict risk control, BTC mandatory confirmation, high win rate priority, suitable for conservative traders',
    promptDescAdaptiveRelaxed: '⚡ Aggressive Strategy (v6.0.0)',
    promptDescAdaptiveRelaxedContent:
      'High-frequency trading, BTC optional confirmation, pursue trading opportunities, suitable for volatile markets',
    promptDescHansen: '🎯 Hansen Strategy',
    promptDescHansenContent:
      'Hansen custom strategy, maximize Sharpe ratio, for professional traders',
    promptDescNof1: '🌐 NoF1 English Framework',
    promptDescNof1Content:
      'Hyperliquid exchange specialist, English prompts, maximize risk-adjusted returns',
    promptDescTaroLong: '📈 Taro Long Position Strategy',
    promptDescTaroLongContent:
      'Data-driven decisions, multi-dimensional validation, continuous learning evolution, long position specialist',

    // Loading & Error
    loading: 'Loading...',

    // AI Traders Page - Additional
    inUse: 'In Use',
    noModelsConfigured: 'No configured AI models',
    noExchangesConfigured: 'No configured exchanges',
    signalSource: 'Signal Source',
    signalSourceConfig: 'Signal Source Configuration',
    ai500Description:
      'API endpoint for AI500 data provider, leave blank to disable this signal source',
    oiTopDescription:
      'API endpoint for open interest rankings, leave blank to disable this signal source',
    information: 'Information',
    signalSourceInfo1:
      '• Signal source configuration is per-user, each user can set their own URLs',
    signalSourceInfo2:
      '• When creating traders, you can choose whether to use these signal sources',
    signalSourceInfo3:
      '• Configured URLs will be used to fetch market data and trading signals',
    editAIModel: 'Edit AI Model',
    addAIModel: 'Add AI Model',
    confirmDeleteModel:
      'Are you sure you want to delete this AI model configuration?',
    cannotDeleteModelInUse:
      'Cannot delete this AI model because it is being used by traders',
    tradersUsing: 'Traders using this configuration',
    pleaseDeleteTradersFirst:
      'Please delete or reconfigure these traders first',
    selectModel: 'Select AI Model',
    pleaseSelectModel: 'Please select a model',
    customBaseURL: 'Base URL (Optional)',
    customBaseURLPlaceholder:
      'Custom API base URL, e.g.: https://api.openai.com/v1',
    leaveBlankForDefault: 'Leave blank to use default API address',
    modelConfigInfo1:
      '• For official API, only API Key is required, leave other fields blank',
    modelConfigInfo2:
      '• Custom Base URL and Model Name only needed for third-party proxies',
    modelConfigInfo3: '• API Key is encrypted and stored securely',
    defaultModel: 'Default model',
    applyApiKey: 'Apply API Key',
    kimiApiNote:
      'Kimi requires API Key from international site (moonshot.ai), China region keys are not compatible',
    leaveBlankForDefaultModel: 'Leave blank to use default model',
    customModelName: 'Model Name (Optional)',
    customModelNamePlaceholder: 'e.g.: deepseek-chat, qwen3-max, gpt-4o',
    saveConfig: 'Save Configuration',
    editExchange: 'Edit Exchange',
    addExchange: 'Add Exchange',
    confirmDeleteExchange:
      'Are you sure you want to delete this exchange configuration?',
    cannotDeleteExchangeInUse:
      'Cannot delete this exchange because it is being used by traders',
    pleaseSelectExchange: 'Please select an exchange',
    exchangeConfigWarning1:
      '• API keys will be encrypted, recommend using read-only or futures trading permissions',
    exchangeConfigWarning2:
      '• Do not grant withdrawal permissions to ensure fund security',
    exchangeConfigWarning3:
      '• After deleting configuration, related traders will not be able to trade',
    edit: 'Edit',
    viewGuide: 'View Guide',
    binanceSetupGuide: 'Binance Setup Guide',
    closeGuide: 'Close',
    whitelistIP: 'Whitelist IP',
    whitelistIPDesc: 'Binance requires adding server IP to API whitelist',
    serverIPAddresses: 'Server IP Addresses',
    copyIP: 'Copy',
    ipCopied: 'IP Copied',
    copyIPFailed: 'Failed to copy IP address. Please copy manually',
    loadingServerIP: 'Loading server IP...',

    // Error Messages
    createTraderFailed: 'Failed to create trader',
    getTraderConfigFailed: 'Failed to get trader configuration',
    modelConfigNotExist: 'Model configuration does not exist or is not enabled',
    exchangeConfigNotExist:
      'Exchange configuration does not exist or is not enabled',
    updateTraderFailed: 'Failed to update trader',
    deleteTraderFailed: 'Failed to delete trader',
    operationFailed: 'Operation failed',
    deleteConfigFailed: 'Failed to delete configuration',
    modelNotExist: 'Model does not exist',
    saveConfigFailed: 'Failed to save configuration',
    exchangeNotExist: 'Exchange does not exist',
    deleteExchangeConfigFailed: 'Failed to delete exchange configuration',
    saveSignalSourceFailed: 'Failed to save signal source configuration',
    encryptionFailed: 'Failed to encrypt sensitive data',

    // Login & Register
    login: 'Sign In',
    register: 'Sign Up',
    username: 'Username',
    email: 'Email',
    password: 'Password',
    confirmPassword: 'Confirm Password',
    usernamePlaceholder: 'your username',
    emailPlaceholder: 'your@email.com',
    passwordPlaceholder: 'Enter your password',
    confirmPasswordPlaceholder: 'Re-enter your password',
    passwordRequirements: 'Password requirements',
    passwordRuleMinLength: 'Minimum 8 characters',
    passwordRuleUppercase: 'At least 1 uppercase letter',
    passwordRuleLowercase: 'At least 1 lowercase letter',
    passwordRuleNumber: 'At least 1 number',
    passwordRuleSpecial: 'At least 1 special character (@#$%!&*?)',
    passwordRuleMatch: 'Passwords match',
    passwordNotMeetRequirements:
      'Password does not meet the security requirements',
    loginTitle: 'Sign in to your account',
    registerTitle: 'Create a new account',
    loginButton: 'Sign In',
    registerButton: 'Sign Up',
    back: 'Back',
    noAccount: "Don't have an account?",
    hasAccount: 'Already have an account?',
    registerNow: 'Sign up now',
    loginNow: 'Sign in now',
    forgotPassword: 'Forgot password?',
    forgotAccount: 'Forgot account?',
    forgotAccountConfirm:
      '⚠️ This will permanently delete EVERYTHING: users, traders, strategies, AI model API keys, exchange API keys, and your CLAW402 wallet. Export anything you need to keep (especially wallet private keys) BEFORE continuing. Re-registration will NOT restore them. Continue?',
    forgotAccountSuccess:
      'Account reset successful! You can now register a new account.',
    rememberMe: 'Remember me',
    resetPassword: 'Reset Password',
    resetPasswordTitle: 'Reset your password',
    newPassword: 'New Password',
    newPasswordPlaceholder: 'Enter new password (at least 6 characters)',
    resetPasswordButton: 'Reset Password',
    resetPasswordSuccess:
      'Password reset successful! Please login with your new password',
    resetPasswordFailed: 'Password reset failed',
    backToLogin: 'Back to Login',
    resetPasswordCliIntro:
      'For security, password recovery is no longer available from the browser. Run this command on the server where AlgoBots is installed:',
    resetPasswordCliSecurityNote:
      'This requires shell access to the server, which keeps your account safe even when AlgoBots is exposed to the internet.',
    resetAccountCliIntro:
      'To wipe everything and start over, run this command on the server where AlgoBots is installed:',
    copy: 'Copy',
    loginSuccess: 'Login successful',
    registrationSuccess: 'Registration successful',
    loginFailed: 'Login failed. Please check your email and password.',
    registrationFailed: 'Registration failed. Please try again.',
    sessionExpired: 'Session expired, please login again',
    invalidCredentials: 'Invalid email or password',
    weak: 'Weak',
    medium: 'Medium',
    strong: 'Strong',
    passwordStrength: 'Password strength',
    passwordStrengthHint:
      'Use at least 8 characters with mix of letters, numbers and symbols',
    passwordMismatch: 'Passwords do not match',
    emailRequired: 'Email is required',
    passwordRequired: 'Password is required',
    invalidEmail: 'Invalid email format',
    passwordTooShort: 'Password must be at least 6 characters',

    // Landing Page
    features: 'Features',
    howItWorks: 'How it Works',
    community: 'Community',
    language: 'Language',
    loggedInAs: 'Logged in as',
    exitLogin: 'Sign Out',
    signIn: 'Sign In',
    signUp: 'Sign Up',
    registrationClosed: 'Registration Closed',
    registrationClosedMessage:
      'User registration is currently disabled. Please contact the administrator for access.',

    // Hero Section
    githubStarsInDays: '2.5K+ GitHub Stars in 3 days',
    heroTitle1: 'Read the Market.',
    heroTitle2: 'Write the Trade.',
    heroDescription:
      'AlgoBots is the future standard for AI trading — an open, community-driven agentic trading OS. Supporting Binance, Aster DEX and other exchanges, self-hosted, multi-agent competition, let AI automatically make decisions, execute and optimize trades for you.',
    poweredBy: 'Powered by Aster DEX and Binance.',

    // Landing Page CTA
    readyToDefine: 'Ready to define the future of AI trading?',
    startWithCrypto:
      'Starting with crypto markets, expanding to TradFi. AlgoBots is the infrastructure of AgentFi.',
    getStartedNow: 'Get Started Now',
    viewSourceCode: 'View Source Code',

    // Features Section
    coreFeatures: 'Core Features',
    whyChooseNofx: 'Why Choose AlgoBots?',
    openCommunityDriven:
      'Open source, transparent, community-driven AI trading OS',
    openSourceSelfHosted: '100% Open Source & Self-Hosted',
    openSourceDesc:
      'Your framework, your rules. Non-black box, supports custom prompts and multi-models.',
    openSourceFeatures1: 'Fully open source code',
    openSourceFeatures2: 'Self-hosting deployment support',
    openSourceFeatures3: 'Custom AI prompts',
    openSourceFeatures4: 'Multi-model support (DeepSeek, Qwen)',
    multiAgentCompetition: 'Multi-Agent Intelligent Competition',
    multiAgentDesc:
      'AI strategies battle at high speed in sandbox, survival of the fittest, achieving strategy evolution.',
    multiAgentFeatures1: 'Multiple AI agents running in parallel',
    multiAgentFeatures2: 'Automatic strategy optimization',
    multiAgentFeatures3: 'Sandbox security testing',
    multiAgentFeatures4: 'Cross-market strategy porting',
    secureReliableTrading: 'Secure and Reliable Trading',
    secureDesc:
      'Enterprise-grade security, complete control over your funds and trading strategies.',
    secureFeatures1: 'Local private key management',
    secureFeatures2: 'Fine-grained API permission control',
    secureFeatures3: 'Real-time risk monitoring',
    secureFeatures4: 'Trading log auditing',

    // About Section
    aboutNofx: 'About AlgoBots',
    whatIsNofx: 'What is AlgoBots?',
    nofxNotAnotherBot:
      "AlgoBots is not another trading bot, but the 'Linux' of AI trading —",
    nofxDescription1:
      'a transparent, trustworthy open source OS that provides a unified',
    nofxDescription2:
      "'decision-risk-execution' layer, supporting all asset classes.",
    nofxDescription3:
      'Starting with crypto markets (24/7, high volatility perfect testing ground), future expansion to stocks, futures, forex. Core: open architecture, AI',
    nofxDescription4:
      'Darwinism (multi-agent self-competition, strategy evolution), CodeFi',
    nofxDescription5:
      'flywheel (developers get point rewards for PR contributions).',
    youFullControl: 'You 100% Control',
    fullControlDesc: 'Complete control over AI prompts and funds',
    startupMessages1: 'Starting automated trading system...',
    startupMessages2: 'API server started on port 8080',
    startupMessages3: 'Web console http://127.0.0.1:3000',

    // How It Works Section
    howToStart: 'How to Get Started with AlgoBots',
    fourSimpleSteps:
      'Four simple steps to start your AI automated trading journey',
    step1Title: 'Clone GitHub Repository',
    step1Desc:
      'git clone https://github.com/patbhakta/algobots-nofx and switch to dev branch to test new features.',
    step2Title: 'Configure Environment',
    step2Desc:
      'Frontend setup for exchange APIs (like Binance, Hyperliquid), AI models and custom prompts.',
    step3Title: 'Deploy & Run',
    step3Desc:
      'One-click Docker deployment, start AI agents. Note: High-risk market, only test with money you can afford to lose.',
    step4Title: 'Optimize & Contribute',
    step4Desc:
      'Monitor trading, submit PRs to improve framework. Join Telegram to share strategies.',
    importantRiskWarning: 'Important Risk Warning',
    riskWarningText:
      'Dev branch is unstable, do not use funds you cannot afford to lose. AlgoBots is non-custodial, no official strategies. Trading involves risks, invest carefully.',

    // Community Section (testimonials are kept as-is since they are quotes)

    // Footer Section
    futureStandardAI: 'The future standard of AI trading',
    links: 'Links',
    resources: 'Resources',
    documentation: 'Documentation',
    supporters: 'Supporters',
    strategicInvestment: '(Strategic Investment)',

    // Login Modal
    accessNofxPlatform: 'Access AlgoBots Platform',
    loginRegisterPrompt:
      'Please login or register to access the full AI trading platform',
    registerNewAccount: 'Register New Account',

    // Candidate Coins Warnings
    candidateCoins: 'Candidate Coins',
    candidateCoinsZeroWarning: 'Candidate Coins Count is 0',
    possibleReasons: 'Possible Reasons:',
    ai500ApiNotConfigured:
      'AI500 data provider API not configured or inaccessible (check signal source settings)',
    apiConnectionTimeout: 'API connection timeout or returned empty data',
    noCustomCoinsAndApiFailed:
      'No custom coins configured and API fetch failed',
    solutions: 'Solutions:',
    setCustomCoinsInConfig: 'Set custom coin list in trader configuration',
    orConfigureCorrectApiUrl: 'Or configure correct data provider API address',
    orDisableAI500Options:
      'Or disable "Use AI500 Data Provider" and "Use OI Top" options',
    signalSourceNotConfigured: 'Signal Source Not Configured',
    signalSourceWarningMessage:
      'You have traders that enabled "Use AI500 Data Provider" or "Use OI Top", but signal source API address is not configured yet. This will cause candidate coins count to be 0, and traders cannot work properly.',
    configureSignalSourceNow: 'Configure Signal Source Now',

    // FAQ Page

    // FAQ Categories

    // ===== GETTING STARTED =====






    // ===== INSTALLATION =====






    // ===== CONFIGURATION =====






    // ===== TRADING =====








    // ===== TECHNICAL ISSUES =====








    // ===== SECURITY =====




    // ===== FEATURES =====



    // ===== AI MODELS =====




    // ===== CONTRIBUTING =====




    // Web Crypto Environment Check
    environmentCheck: {
      button: 'Check Secure Environment',
      checking: 'Checking...',
      description:
        'Automatically verifying whether this browser context allows Web Crypto before entering sensitive keys.',
      secureTitle: 'Secure context detected',
      secureDesc:
        'Web Crypto API is available. You can continue entering secrets with encryption enabled.',
      insecureTitle: 'Insecure context detected',
      insecureDesc:
        'This page is not running over HTTPS or a trusted localhost origin, so browsers block Web Crypto calls.',
      tipsTitle: 'How to fix:',
      tipHTTPS:
        'Serve the dashboard over HTTPS with a valid certificate (IP origins also need TLS).',
      tipLocalhost:
        'During development, open the app via http://localhost or 127.0.0.1.',
      tipIframe:
        'Avoid embedding the app in insecure HTTP iframes or reverse proxies that strip HTTPS.',
      unsupportedTitle: 'Browser does not expose Web Crypto',
      unsupportedDesc:
        'Open AlgoBots over HTTPS (or http://localhost during development) and avoid insecure iframes/reverse proxies so the browser can enable Web Crypto.',
      summary: 'Current origin: {origin} • Protocol: {protocol}',
      disabledTitle: 'Transport encryption disabled',
      disabledDesc:
        'Server-side transport encryption is disabled. API keys will be transmitted in plaintext. Enable TRANSPORT_ENCRYPTION=true for enhanced security.',
    },

    environmentSteps: {
      checkTitle: '1. Environment check',
      selectTitle: '2. Select exchange',
    },

    // Two-Stage Key Modal
    twoStageKey: {
      title: 'Two-Stage Private Key Input',
      stage1Description:
        'Enter the first {length} characters of your private key',
      stage2Description:
        'Enter the remaining {length} characters of your private key',
      stage1InputLabel: 'First Part',
      stage2InputLabel: 'Second Part',
      characters: 'characters',
      processing: 'Processing...',
      nextButton: 'Next',
      cancelButton: 'Cancel',
      backButton: 'Back',
      encryptButton: 'Encrypt & Submit',
      obfuscationCopied: 'Obfuscation data copied to clipboard',
      obfuscationInstruction:
        'Paste something else to clear clipboard, then continue',
      obfuscationManual: 'Manual obfuscation required',
    },

    // Error Messages
    errors: {
      privatekeyIncomplete: 'Please enter at least {expected} characters',
      privatekeyInvalidFormat:
        'Invalid private key format (should be 64 hex characters)',
      privatekeyObfuscationFailed: 'Clipboard obfuscation failed',
    },

    // Position History
    positionHistory: {
      title: 'Position History',
      loading: 'Loading position history...',
      noHistory: 'No Position History',
      noHistoryDesc: 'Closed positions will appear here after trading.',
      showingPositions: 'Showing {count} of {total} positions',
      totalPnL: 'Total P&L',
      // Stats
      totalTrades: 'Total Trades',
      winLoss: 'Win: {win} / Loss: {loss}',
      winRate: 'Win Rate',
      profitFactor: 'Profit Factor',
      profitFactorDesc: 'Total Profit / Total Loss',
      plRatio: 'P/L Ratio',
      plRatioDesc: 'Avg Win / Avg Loss',
      sharpeRatio: 'Sharpe Ratio',
      sharpeRatioDesc: 'Risk-adjusted Return',
      maxDrawdown: 'Max Drawdown',
      avgWin: 'Avg Win',
      avgLoss: 'Avg Loss',
      netPnL: 'Net P&L',
      netPnLDesc: 'After Fees',
      fee: 'Fee',
      // Direction Stats
      trades: 'Trades',
      avgPnL: 'Avg P&L',
      // Symbol Performance
      symbolPerformance: 'Symbol Performance',
      // Filters
      symbol: 'Symbol',
      allSymbols: 'All Symbols',
      side: 'Side',
      all: 'All',
      sort: 'Sort',
      latestFirst: 'Latest First',
      oldestFirst: 'Oldest First',
      highestPnL: 'Highest P&L',
      lowestPnL: 'Lowest P&L',
      // Table Headers
      entry: 'Entry',
      exit: 'Exit',
      qty: 'Qty',
      value: 'Value',
      lev: 'Lev',
      pnl: 'P&L',
      duration: 'Duration',
      closedAt: 'Closed At',
    },

    // Data Page
    dataCenter: 'Data Center',

    // Strategy Market Page
    strategyMarket: {
      title: 'STRATEGY MARKET',
      subtitle: 'GLOBAL STRATEGY DATABASE',
      description:
        'Discover, analyze, and clone high-performance trading algorithms',
      search: 'SEARCH PARAMETERS...',
      all: 'ALL PROTOCOLS',
      popular: 'TRENDING',
      recent: 'LATEST',
      myStrategies: 'MY LIBRARY',
      noStrategies: 'NO SIGNAL',
      noStrategiesDesc: 'No strategic signals detected in this frequency',
      author: 'OPERATOR',
      createdAt: 'TIMESTAMP',
      viewConfig: 'DECRYPT CONFIG',
      hideConfig: 'ENCRYPT',
      copyConfig: 'CLONE CONFIG',
      copied: 'COPIED',
      configHidden: 'ENCRYPTED',
      configHiddenDesc: 'Configuration parameters encrypted',
      indicators: 'INDICATORS',
      maxPositions: 'POS_LIMIT',
      maxLeverage: 'LEV_MAX',
      shareYours: 'UPLOAD_STRATEGY',
      makePublic: 'PUBLISH',
      loading: 'INITIALIZING...',
    },

    // Strategy Studio Page
    strategyStudio: {
      title: 'Strategy Studio',
      subtitle: 'Configure and test trading strategies',
      strategies: 'Strategies',
      newStrategy: 'New',
      strategyType: 'Strategy Type',
      aiTrading: 'AI Trading',
      aiTradingDesc: 'AI analyzes market and makes trading decisions',
      gridTrading: 'AI Grid Trading',
      gridTradingDesc: 'AI-controlled grid strategy for ranging markets',
      gridConfig: 'Grid Configuration',
      coinSource: 'Coin Source',
      indicators: 'Indicators',
      riskControl: 'Risk Control',
      promptSections: 'Prompt Editor',
      customPrompt: 'Extra Prompt',
      save: 'Save',
      saving: 'Saving...',
      activate: 'Activate',
      active: 'Active',
      default: 'Default',
      promptPreview: 'Prompt Preview',
      aiTestRun: 'AI Test',
      systemPrompt: 'System Prompt',
      userPrompt: 'User Prompt',
      loadPrompt: 'Generate Prompt',
      refreshPrompt: 'Refresh',
      promptVariant: 'Style',
      balanced: 'Balanced',
      aggressive: 'Aggressive',
      conservative: 'Conservative',
      selectModel: 'Select AI Model',
      runTest: 'Run AI Test',
      running: 'Running...',
      aiOutput: 'AI Output',
      reasoning: 'Reasoning',
      decisions: 'Decisions',
      duration: 'Duration',
      noModel: 'Please configure AI model first',
      testNote: 'Test with real AI, no trading',
      publishSettings: 'Publish',
      newStrategyName: 'New Strategy',
      strategyCopy: 'Strategy Copy',
      strategyDeleted: 'Strategy deleted',
      cannotDeleteActiveStrategy: 'Active strategy cannot be deleted',
      confirmDeleteStrategy: 'Delete this strategy?',
      confirmDelete: 'Confirm Delete',
      delete: 'Delete',
      cancel: 'Cancel',
      strategyExported: 'Strategy exported',
      invalidStrategyFile: 'Invalid strategy file',
      imported: 'Imported',
      strategyImported: 'Strategy imported',
      strategySaved: 'Strategy saved',
      importStrategy: 'Import Strategy',
      newStrategyTooltip: 'New Strategy',
      export: 'Export',
      duplicate: 'Duplicate',
      deleteTooltip: 'Delete',
      public: 'Public',
      addDescription: 'Add strategy description...',
      unsaved: 'Unsaved',
      discardChanges: 'Discard',
      selectOrCreate: 'Select or create a strategy',
      customPromptDesc:
        'Extra prompt appended to System Prompt for personalized trading style',
      customPromptPlaceholder: 'Enter custom prompt...',
      generatePromptPreview: 'Click to generate prompt preview',
      runAiTestHint: 'Click to run AI test',
      tokenEstimate: 'Token Estimate',
      tokenExceedWarning:
        'Token estimate exceeds 128K. AI requests may fail for some models.',
      tokenEstimating: 'Estimating...',
      tokenTooltip: 'Based on 200K context',
    },

    // Metric Tooltip
    metricTooltip: {
      formula: 'Formula',
    },

    // Login Required Overlay
    loginRequired: {
      title: 'SYSTEM ACCESS DENIED',
      accessDenied: 'ACCESS DENIED',
      subtitleWithFeature:
        'Module "{featureName}" requires elevated privileges',
      subtitleDefault: 'Authorization required for this module',
      description:
        'Initialize authentication protocol to unlock full system capabilities: AI Trader configuration and Strategy Market data streams.',
      benefit1: 'AI Trader Control',
      benefit2: 'HFT Strategy Market',
      benefit4: 'Full System Visualization',
      loginButton: 'EXECUTE LOGIN',
      registerButton: 'REGISTER NEW ID',
      abort: 'ABORT',
    },

    // Advanced Chart
    advancedChart: {
      updating: 'Updating...',
      indicators: 'Indicators',
      orderMarkers: 'Order Markers',
      technicalIndicators: 'Technical Indicators',
      clickToToggle: 'Click to toggle indicators',
      shares: 'shares',
      units: 'units',
    },

    // Chart With Orders
    chartWithOrders: {
      failedToLoad: 'Failed to load chart data',
      loading: 'Loading...',
      buy: 'BUY',
      sell: 'SELL',
    },

    // Comparison Chart
    comparisonChart: {
      '1d': '1D',
      '3d': '3D',
      '7d': '7D',
      '30d': '30D',
      all: 'All',
    },

    // TraderDashboardPage
    traderDashboard: {
      connectionFailed: 'Connection Failed',
      connectionFailedDesc: 'Please check if the backend service is running.',
      retry: 'Retry',
      confirmClosePosition:
        'Are you sure you want to close {symbol} {side} position?',
      confirmClose: 'Confirm Close',
      confirm: 'Confirm',
      cancel: 'Cancel',
      positionClosed: 'Position closed successfully',
      closeFailed: 'Failed to close position',
      closeAll: 'Close All',
      confirmCloseAllPositions:
        'Market-close ALL {count} open positions?',
      allPositionsClosed: 'All positions closed',
      closeAllPartial: '{failed} of {count} positions failed to close',
      hideAddress: 'Hide address',
      showFullAddress: 'Show full address',
      copyAddress: 'Copy address',
      noAddressConfigured: 'No address configured',
      action: 'Action',
      entry: 'Entry',
      mark: 'Mark',
      qty: 'Qty',
      value: 'Value',
      lev: 'Lev.',
      uPnL: 'uPnL',
      liq: 'Liq.',
      closePosition: 'Close Position',
      close: 'Close',
      showingPositions: 'Showing {shown} of {total} positions',
      perPage: 'Per page',
      accountFetchFailed:
        'DATA_FETCH::FAILED — Account data unavailable, check connection',
      positionsFetchFailed: 'Position data unavailable',
      decisionsFetchFailed: 'Decision data unavailable',
    },

    // AITradersPage toast messages
    aiTradersToast: {
      creating: 'Creating...',
      created: 'Created successfully',
      createFailed: 'Creation failed',
      saving: 'Saving...',
      saved: 'Saved successfully',
      saveFailed: 'Save failed',
      deleting: 'Deleting...',
      deleted: 'Deleted successfully',
      deleteFailed: 'Deletion failed',
      stopping: 'Stopping...',
      stopped: 'Stopped',
      stopFailed: 'Stop failed',
      starting: 'Starting...',
      started: 'Started',
      startFailed: 'Start failed',
      updating: 'Updating...',
      updatingConfig: 'Updating config...',
      configUpdated: 'Config updated',
      configUpdateFailed: 'Config update failed',
      showInCompetition: 'Shown in competition',
      hideInCompetition: 'Hidden from competition',
      updateFailed: 'Update failed',
      updatingModelConfig: 'Updating model config...',
      modelConfigUpdated: 'Model config updated',
      modelConfigUpdateFailed: 'Model config update failed',
      deletingExchange: 'Deleting exchange account...',
      exchangeDeleted: 'Exchange account deleted',
      exchangeDeleteFailed: 'Failed to delete exchange account',
      updatingExchangeConfig: 'Updating exchange config...',
      exchangeConfigUpdated: 'Exchange config updated',
      exchangeConfigUpdateFailed: 'Failed to update exchange config',
      creatingExchange: 'Creating exchange account...',
      exchangeCreated: 'Exchange account created',
      exchangeCreateFailed: 'Failed to create exchange account',
    },

    // ModelConfigModal
    modelConfig: {
      selectModel: 'Select Model',
      configure: 'Configure',
      configureApi: 'Configure API',
      configureWallet: 'Configure Wallet',
      chooseProvider: 'Choose Your AI Provider',
      claw402EntryDesc:
        'Recommended default path. Use Base USDC pay-per-call instead of managing API keys.',
      otherApiEntry: 'Other API Providers',
      otherApiEntryDesc:
        'Use your own API key for OpenAI, Claude, Gemini, DeepSeek, and more.',
      payPerCall: 'Pay-as-you-go USDC · All AI Models · No API Key',
      recommended: 'Best',
      allModelsClaw: 'Pay-as-you-go with USDC — supports all major AI models',
      selectAiModel: 'Choose AI Model',
      allModelsUnified:
        'All models unified via Claw402. Switch anytime after setup.',
      setupWallet: 'Setup Wallet',
      walletInfo: 'Claw402 uses USDC on Base chain. You need an EVM wallet.',
      exportKey: 'Export private key from MetaMask, Rabby, etc.',
      dedicatedWallet:
        'Recommended: create a dedicated wallet with a small USDC balance',
      walletPrivateKey: 'Wallet Private Key (Base Chain EVM)',
      privateKeyNote:
        'Private key is only used locally for signing. Never uploaded. No ETH or gas needed.',
      howToFundUsdc: 'How to Fund USDC',
      fundStep1:
        'Withdraw USDC from exchange (Binance/OKX/Coinbase) to your wallet',
      fundStep2: 'Select Base network (very low fees)',
      fundStep3: '$5-10 USDC lasts a long time (~$0.003/call)',
      back: 'Back',
      startTrading: 'Start Trading',
      modelsConfigured: 'Models with gold badge are already configured',
      getStarted: 'Get Started',
      getApiKey: 'Get API Key',
      walletPrivateKeyLabel: 'Wallet Private Key *',
      selectModelLabel: 'Select Model',
      validating: 'Validating...',
      walletAddress: 'Wallet Address',
      usdcBalance: 'Base USDC Balance',
      claw402Connected: 'claw402 Connected',
      claw402Unreachable: 'claw402 Unreachable',
      depositUsdc: 'Deposit USDC to this address on Base chain',
      invalidKeyPrefix: 'Please add 0x at the beginning',
      invalidKeyLength: 'Should be 66 characters, currently',
      invalidKeyChars: 'Contains invalid characters',
      testConnection: 'Test Connection',
      testingConnection: 'Testing...',
    },

    // ExchangeConfigModal
    exchangeConfig: {
      selectExchange: 'Select Exchange',
      configure: 'Configure',
      chooseExchange: 'Choose Your Exchange',
      centralizedExchanges: 'Centralized Exchanges',
      decentralizedExchanges: 'Decentralized Exchanges',
      register: 'Register',
      bonus: 'Bonus',
      accountName: 'Account Name',
      accountNamePlaceholder: 'e.g., Main Account',
      pleaseEnterAccountName: 'Please enter account name',
      useBinanceFuturesApi: 'Use "Spot & Futures Trading" API',
      viewTutorial: 'View Tutorial',
      lighterApiKeySetup: 'Lighter API Key Setup',
      lighterApiKeyDesc: 'Generate an API Key on Lighter website',
      apiKeyIndex: 'API Key Index',
      apiKeyIndexTooltip: 'API Key index starts from 0',
      back: 'Back',
    },

    // TelegramConfigModal
    telegram: {
      botSetup: 'Telegram Bot Setup',
      createBot: 'Create Bot',
      bindAccount: 'Bind Account',
      done: 'Done',
      invalidTokenFormat:
        'Invalid Bot Token format. Expected "numbers:alphanumeric"',
      tokenSaved: 'Bot Token saved, waiting for binding',
      saveFailed: 'Save failed, please verify the token',
      unbound: 'Telegram account unbound',
      unbindFailed: 'Unbind failed',
      step1Title: 'Step 1: Create your Bot in Telegram',
      step1Desc1: 'Open Telegram, search for',
      step1Desc2: 'Send',
      step1Desc2Suffix: 'command',
      step1Desc3: 'Follow prompts to set bot name and username',
      step1Desc4: 'BotFather will return a Token, copy it',
      openBotFather: 'Open @BotFather',
      pasteToken: 'Paste Bot Token',
      tokenFormat: 'Format: numbers:alphanumeric, e.g. 123456789:ABCdef...',
      selectAiModel: 'Select AI Model (optional)',
      noEnabledModels: 'No enabled models. Configure one in AI Models first.',
      autoSelect: '— Auto-select (recommended)',
      autoUseEnabled: 'Leave blank to auto-use any enabled model',
      savingToken: 'Saving...',
      saveAndContinue: 'Save & Continue',
      step2Title: 'Step 2: Send /start to your Bot',
      step2Desc1: 'Search for your newly created Bot in Telegram',
      step2Desc2: 'Click Start or send',
      step2Desc3: 'Bot will automatically bind to your account',
      currentToken: 'Current Token',
      waitingForStart:
        'Waiting for you to send /start... Refresh page after sending',
      reconfigureToken: 'Reconfigure Token',
      bindSuccess: 'Bound successfully!',
      noStartReceived:
        'No /start received yet. Please send /start to your Bot first',
      checkFailed: 'Check failed',
      checkStatus: 'Check Status',
      botActive: 'Telegram Bot is Active!',
      botActiveDesc:
        'You can now control the trading system via natural language in Telegram',
      supportedCommands: 'Supported Commands',
      cmdHelp: 'Show all commands',
      cmdStatus: 'Show trader status',
      cmdNaturalLang: 'Natural language',
      cmdStartStop: 'Start/stop trader',
      cmdControl: 'Natural language control',
      cmdPositions: 'View positions',
      cmdPositionsDesc: 'Real-time position query',
      cmdStrategy: 'Configure strategy',
      cmdStrategyDesc: 'Modify trading strategy',
      unbinding: 'Unbinding...',
      unbindAccount: 'Unbind Account',
      aiModelLabel: 'AI Model (for natural language)',
      aiModelAutoSelect: '— Auto-select',
      modelUpdated: 'AI model updated',
      modelUpdateFailed: 'Update failed',
      save: 'Save',
      loading: 'Loading...',
    },

    // TraderConfigViewModal
    traderConfigView: {
      traderConfig: 'Trader Configuration',
      configInfo: '{name} configuration details',
      running: 'Running',
      stopped: 'Stopped',
      basicInfo: 'Basic Information',
      traderName: 'Trader Name',
      aiModel: 'AI Model',
      exchange: 'Exchange',
      initialBalance: 'Initial Balance',
      marginMode: 'Margin Mode',
      crossMargin: 'Cross',
      isolatedMargin: 'Isolated',
      scanInterval: '{minutes} minutes',
      scanIntervalLabel: 'Scan Interval',
      strategyUsed: 'Strategy Used',
      strategyName: 'Strategy Name',
      close: 'Close',
      yes: 'Yes',
      no: 'No',
    },
  },
}

export function t(
  key: string,
  lang: Language,
  params?: Record<string, string | number>
): string {
  // Handle nested keys like 'twoStageKey.title'
  const keys = key.split('.')
  let value: any = translations[lang]

  for (const k of keys) {
    value = value?.[k]
  }

  let text = typeof value === 'string' ? value : key

  // Replace parameters like {count}, {gap}, etc.
  if (params) {
    Object.entries(params).forEach(([param, value]) => {
      text = text.replace(`{${param}}`, String(value))
    })
  }

  return text
}
