

---




---



---






```

                            ↑
```












|----------|:------:|:-------:|:-------:|:-----:|:----:|
| FinGPT | ❌ | ❌ | ❌ | ❌ | ✅ |
| BloombergGPT | ❌ | ❌ | ❌ | ❌ | ❌ |
| FinRL | ❌ | ❌ | ❌ | ✅ | ✅ |
| TradingGPT | ❌ | ❌ | ✅ | ❌ | ❌ |
| **AI-Trader** | ✅ | ✅ | ✅ | ✅ | ✅ |

---






|---------|------|



|------|---------|---------|---------|---------|



|-------|------|---------|------|

---







```
┌────────────────────────────────────────────────────────────────────┐
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    │
│  │          │    │          │    │          │    │          │    │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘    │
│                                                                    │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌──────────┐    ┌──────────────────────────────┐    ┌──────────┐ │
│  │          │    │                              │    │          │ │
│  └──────────┘    └──────────────────────────────┘    └──────────┘ │
│                                                                    │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```



```python
minimal_context = {
        "AAPL": {"quantity": 100, "avg_price": 150.0},
        ...
    },
        "get_price",
        "search_news",
        "execute_trade",
        "calculate"
    ]
}
```







---



```
┌─────────────────────────────────────────────────────────────────────────┐
│                         AI-Trader System Architecture                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      Presentation Layer                          │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │   │
│  │  │  Web Dashboard  │  │   Leaderboard   │  │  Reasoning View │  │   │
│  │  │  (ai4trade.ai)  │  │                 │  │                 │  │   │
│  │  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘  │   │
│  └───────────┼────────────────────┼────────────────────┼───────────┘   │
│              │                    │                    │               │
│              └────────────────────┼────────────────────┘               │
│                                   │                                     │
│                                   ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    Agent Orchestration Layer                     │   │
│  │                                                                   │   │
│  │   ┌──────────────────────────────────────────────────────────┐   │   │
│  │   │                    Agent Factory                          │   │   │
│  │   │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐     │   │   │
│  │   │  │US Agent │  │CN Agent │  │Crypto   │  │Custom   │     │   │   │
│  │   │  │         │  │         │  │Agent    │  │Agent    │     │   │   │
│  │   │  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘     │   │   │
│  │   │       └────────────┼────────────┴────────────┘           │   │   │
│  │   │                    │                                      │   │   │
│  │   │                    ▼                                      │   │   │
│  │   │  ┌──────────────────────────────────────────────────┐    │   │   │
│  │   │  │              BaseAgent (Core)                     │    │   │   │
│  │   │  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  │    │   │   │
│  │   │  │  │ ReAct Loop │  │Tool Manager│  │State Tracker│  │    │   │   │
│  │   │  │  └────────────┘  └────────────┘  └────────────┘  │    │   │   │
│  │   │  └──────────────────────────────────────────────────┘    │   │   │
│  │   └──────────────────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                   │                                     │
│                                   ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      MCP Tool Services Layer                     │   │
│  │                                                                   │   │
│  │   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │   │
│  │   │tool_trade│ │tool_price│ │tool_search│ │tool_math│           │   │
│  │   │  :8001   │ │  :8002   │ │   :8003  │ │  :8004   │           │   │
│  │   │          │ │          │ │          │ │          │           │   │
│  │   └──────────┘ └──────────┘ └──────────┘ └──────────┘           │   │
│  │                                                                   │   │
│  │   ┌──────────┐ ┌──────────┐                                      │   │
│  │   │tool_news │ │tool_crypto│                                     │   │
│  │   │  :8005   │ │  :8006   │                                      │   │
│  │   │          │ │          │                                      │   │
│  │   └──────────┘ └──────────┘                                      │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                   │                                     │
│                                   ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      Data Infrastructure Layer                   │   │
│  │                                                                   │   │
│  │   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │   │
│  │   │Alpha Vantage │  │   Tushare    │  │  Local JSONL │          │   │
│  │   │              │  │              │  │              │          │   │
│  │   │ • US Stocks  │  │ • A-Shares   │  │ • Historical │          │   │
│  │   │ • Crypto     │  │ • CN Market  │  │ • Cache      │          │   │
│  │   │ • News API   │  │ • Holidays   │  │ • Replay     │          │   │
│  │   └──────────────┘  └──────────────┘  └──────────────┘          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                   │                                     │
│                                   ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      LLM Provider Layer                          │   │
│  │                                                                   │
│  │   ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐       │   │
│  │   │ GPT-4o │ │Claude-3│ │DeepSeek│ │ Gemini │ │  Qwen  │       │   │
│  │   └────────┘ └────────┘ └────────┘ └────────┘ └────────┘       │   │
│  │                                                                   │   │
│  │   ┌────────┐ ┌────────┐ ┌────────┐                              │   │
│  │   │Llama-3 │ │ Mixtral│ │ Custom │                              │   │
│  │   └────────┘ └────────┘ └────────┘                              │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```


```
AI-Trader/
│
│
│
│
│   │   └── {symbol}_{date}.jsonl
│   │   └── {symbol}_{date}.jsonl
│       └── {symbol}_{date}.jsonl
│
│
│
```


|------|------|------|---------|


```
┌────────────────────────────────────────────────────────────────────────┐
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌──────────────┐                                                      │
│  └──────────────┘                           │                          │
│                                             ▼                          │
│  ┌──────────────┐     ┌──────────────┐    ┌──────────────┐            │
│  │ Date/Assets │  +  │  Positions   │  + │    Tools     │            │
│  └──────────────┘     └──────────────┘    └──────────────┘            │
│         │                   │                   │                      │
│         └───────────────────┼───────────────────┘                      │
│                             ▼                                          │
│                    ┌─────────────────┐                                 │
│                    │ System Prompt   │                                 │
│                    └────────┬────────┘                                 │
│                             │                                          │
│                             ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │                                                                  │  │
│  │   ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────────┐ │  │
│  │   │ Thought │ →  │ Action  │ →  │Observat.│ →  │ Thought...  │ │  │
│  │   │         │    │(Tool    │    │(Tool    │    │             │ │  │
│  │   └─────────┘    └────┬────┘    └────┬────┘    └─────────────┘ │  │
│  │                       │              ▲                          │  │
│  │                       ▼              │                          │  │
│  │                 ┌─────────────────────────┐                     │  │
│  │                 │     MCP Tool Service    │                     │  │
│  │                 │  • get_price            │                     │  │
│  │                 │  • search_news          │                     │  │
│  │                 │  • execute_trade        │                     │  │
│  │                 └─────────────────────────┘                     │  │
│  │                                                                  │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                             │                                          │
│                             ▼                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐            │
│  │              │    │              │    │              │            │
│  └──────────────┘    └──────────────┘    └──────────────┘            │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---



```python
class BaseAgent:
    """


    Attributes:

    """

    def __init__(
        self,
        signature: str,
        basemodel: str,
        stock_symbols: List[str] = NASDAQ_100,
        mcp_config: dict = None,
        max_steps: int = 10,
        initial_cash: float = 10000.0,
        market: str = "us",
        verbose: bool = False
    ):
        self.signature = signature
        self.basemodel = basemodel
        self.stock_symbols = stock_symbols
        self.max_steps = max_steps
        self.initial_cash = initial_cash
        self.market = market
        self.verbose = verbose

        self.llm = None
        self.tools = []
        self.mcp_client = None
        self.portfolio = Portfolio(initial_cash)
        self.logger = setup_logger(signature)
```


```python
async def initialize(self):
    """

    """
    self.mcp_client = MCPClient()
    await self.mcp_client.connect(self.mcp_config)

    self.tools = await self.mcp_client.list_tools()
    self.logger.info(f"Loaded {len(self.tools)} tools: {[t.name for t in self.tools]}")

    self.llm = self._create_llm_client()

    self.llm = self.llm.bind_tools(
        self.tools,
    )

def _create_llm_client(self):
    """

    """
    model_lower = self.basemodel.lower()

    if "deepseek" in model_lower:
        return DeepSeekChatOpenAI(
            model=self.basemodel,
            temperature=0.7,
            api_key=os.environ.get("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com/v1"
        )
    elif "claude" in model_lower:
        return ChatAnthropic(
            model=self.basemodel,
            temperature=0.7,
            api_key=os.environ.get("ANTHROPIC_API_KEY")
        )
    elif "gemini" in model_lower:
        return ChatGoogleGenerativeAI(
            model=self.basemodel,
            temperature=0.7,
            api_key=os.environ.get("GOOGLE_API_KEY")
        )
    else:
        return ChatOpenAI(
            model=self.basemodel,
            temperature=0.7,
            api_key=os.environ.get("OPENAI_API_KEY")
        )
```


```python
def _build_system_prompt(self, date: str) -> str:
    """

    """
    positions_str = self._format_positions()
    tools_str = self._format_tools()

    return f"""You are an autonomous trading agent operating in the {self.market} market.

## Current Date
{date}

## Your Portfolio
- Available Cash: ${self.portfolio.cash:.2f}
- Current Positions:
{positions_str}

## Tradable Assets
{', '.join(self.stock_symbols)}

## Available Tools
{tools_str}

## Trading Rules
- You operate in {self.market} market
- Settlement: {'T+0 (can sell same day)' if self.market != 'cn' else 'T+1 (can only sell next day)'}
- Trading Hours: {'24/7' if self.market == 'crypto' else '9:30-16:00'}

## Instructions
1. Use the available tools to gather information before making decisions
2. Think step by step about market conditions
3. Consider risk management in your decisions
4. Explain your reasoning clearly
5. When ready to finalize decisions for today, output [STOP]

## Important
- You MUST search for relevant information before making trading decisions
- Do NOT assume any market information - use tools to verify
- Consider multiple sources of information
- Be explicit about your reasoning process"""
```


```python
async def run_trading_session(self, date: str) -> TradingSessionResult:
    """


    Args:

    Returns:
    """
    self.logger.info(f"Starting trading session for {date}")

    system_prompt = self._build_system_prompt(date)
    messages = [SystemMessage(content=system_prompt)]

    reasoning_chain = []

    for step in range(self.max_steps):
        step_record = {
            "step": step + 1,
            "timestamp": datetime.now().isoformat(),
            "thought": None,
            "action": None,
            "observation": None
        }

        try:
            response = await self._ainvoke_with_retry(messages)

            step_record["thought"] = response.content

            if response.tool_calls:
                tool_results = []

                for tool_call in response.tool_calls:
                    step_record["action"] = {
                        "tool": tool_call["name"],
                        "arguments": tool_call["args"]
                    }

                    result = await self._execute_tool(tool_call)
                    tool_results.append({
                        "tool_call_id": tool_call["id"],
                        "result": result
                    })

                    step_record["observation"] = result

                messages.append(AIMessage(
                    content=response.content or "",
                    tool_calls=response.tool_calls
                ))

                for tr in tool_results:
                    messages.append(ToolMessage(
                        content=str(tr["result"]),
                        tool_call_id=tr["tool_call_id"]
                    ))
            else:
                messages.append(response)

            reasoning_chain.append(step_record)

            if self._should_stop(response):
                self.logger.info(f"Agent decided to stop at step {step + 1}")
                break

        except Exception as e:
            self.logger.error(f"Step {step + 1} failed: {e}")
            step_record["error"] = str(e)
            reasoning_chain.append(step_record)
            continue

    decisions = self._extract_decisions(messages)

    execution_results = await self._execute_decisions(decisions, date)

    result = TradingSessionResult(
        date=date,
        decisions=decisions,
        execution_results=execution_results,
        reasoning_chain=reasoning_chain,
        final_portfolio=self.portfolio.snapshot(),
        steps_taken=len(reasoning_chain),
        tokens_used=self._count_tokens(messages)
    )

    self._save_session_result(result)

    return result

def _should_stop(self, response) -> bool:
    if response.content and "[STOP]" in response.content:
        return True
    return False
```


```python
async def _execute_tool(self, tool_call: dict) -> Any:
    """

    Args:
            {
                "id": "call_xxx",
                "name": "get_price",
                "args": {"symbol": "AAPL", "data_type": "current"}
            }

    Returns:
    """
    tool_name = tool_call["name"]
    tool_args = tool_call["args"]

    self.logger.debug(f"Executing tool: {tool_name} with args: {tool_args}")

    try:
        result = await self.mcp_client.call_tool(tool_name, tool_args)

        self.logger.debug(f"Tool result: {result}")
        return result

    except ToolExecutionError as e:
        self.logger.warning(f"Tool {tool_name} execution failed: {e}")
        return {"error": str(e)}
    except TimeoutError:
        self.logger.warning(f"Tool {tool_name} timed out")
        return {"error": "Tool execution timed out"}
```


```python
async def _ainvoke_with_retry(
    self,
    messages: List[BaseMessage],
    max_retries: int = 3,
    base_delay: float = 1.0
) -> AIMessage:
    """


    Args:

    Returns:

    Raises:
    """
    last_exception = None

    for attempt in range(max_retries):
        try:
            response = await self.llm.ainvoke(messages)
            return response

        except RateLimitError as e:
            last_exception = e
            self.logger.warning(
                f"Rate limited, retry {attempt + 1}/{max_retries} after {delay}s"
            )
            await asyncio.sleep(delay)

        except APIError as e:
            last_exception = e
            error_msg = str(e).lower()

            if "overloaded" in error_msg or "503" in error_msg:
                delay = base_delay * (2 ** attempt)
                self.logger.warning(
                    f"Server overloaded, retry {attempt + 1}/{max_retries} after {delay}s"
                )
                await asyncio.sleep(delay)
            else:
                raise

        except TimeoutError as e:
            last_exception = e
            delay = base_delay * (2 ** attempt)
            self.logger.warning(
                f"Request timeout, retry {attempt + 1}/{max_retries} after {delay}s"
            )
            await asyncio.sleep(delay)

    self.logger.error(f"All {max_retries} retries failed")
    raise last_exception
```



```python
class DeepSeekChatOpenAI(ChatOpenAI):
    """

    """

    def _fix_tool_calls(self, response: AIMessage) -> AIMessage:
        """

        """
        if not response.tool_calls:
            return response

        fixed_tool_calls = []
        for tc in response.tool_calls:
            fixed_tc = tc.copy()

            if isinstance(tc.get("args"), str):
                try:
                    fixed_tc["args"] = json.loads(tc["args"])
                except json.JSONDecodeError:
                    self.logger.warning(
                        f"Failed to parse tool arguments: {tc['args']}"
                    )

            fixed_tool_calls.append(fixed_tc)

        response.tool_calls = fixed_tool_calls
        return response

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> ChatResult:
        result = super()._generate(messages, stop, **kwargs)

        for generation in result.generations:
            if hasattr(generation, 'message'):
                generation.message = self._fix_tool_calls(generation.message)

        return result

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> ChatResult:
        result = await super()._agenerate(messages, stop, **kwargs)

        for generation in result.generations:
            if hasattr(generation, 'message'):
                generation.message = self._fix_tool_calls(generation.message)

        return result
```

---




```
┌────────────────────────────────────────────────────────────────────┐
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌────────────────┐                      ┌────────────────┐       │
│  │   MCP Client   │                      │   MCP Server   │       │
│  │                │                      │                │       │
│  │                │                      │                │       │
│  └────────────────┘                      └────────────────┘       │
│                                                                    │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```



```python
from fastmcp import FastMCP, tool

mcp = FastMCP("trade_service")

@mcp.tool()
async def execute_trade(
    symbol: str,
    action: Literal["buy", "sell"],
    quantity: float,
    order_type: Literal["market", "limit"] = "market",
    limit_price: Optional[float] = None
) -> dict:
    """

    Args:

    Returns:
        {
            "success": True/False,
            "order_id": "ord_xxx",
            "symbol": "AAPL",
            "action": "buy",
            "order_type": "market",
            "requested_quantity": 100,
            "filled_quantity": 100,
            "filled_price": 150.25,
            "commission": 0.01,
            "timestamp": "2024-12-28T10:30:00Z",
            "message": "Order executed successfully"
        }

    Raises:
    """
    context = get_simulation_context()

    market_rules = get_market_rules(symbol)

    if not market_rules.is_trading_hours(context.current_time):
        return {
            "success": False,
            "error": "MarketClosedError",
            "message": f"Market is closed. Trading hours: {market_rules.trading_hours}"
        }

    if action == "sell" and market_rules.settlement == "T+1":
        position = context.portfolio.get_position(symbol)
        if position and position.buy_date == context.current_date:
            return {
                "success": False,
                "error": "T1RestrictionError",
                "message": "Cannot sell shares bought today (T+1 settlement)"
            }

    if action == "buy":
        current_price = await get_current_price(symbol)
        required_funds = current_price * quantity * (1 + market_rules.commission_rate)

        if required_funds > context.portfolio.available_cash:
            return {
                "success": False,
                "error": "InsufficientFundsError",
                "message": f"Insufficient funds. Required: ${required_funds:.2f}, Available: ${context.portfolio.available_cash:.2f}"
            }
    else:  # sell
        position = context.portfolio.get_position(symbol)
        if not position or position.quantity < quantity:
            available = position.quantity if position else 0
            return {
                "success": False,
                "error": "InsufficientPositionError",
                "message": f"Insufficient position. Requested: {quantity}, Available: {available}"
            }

    filled_price = await simulate_execution(symbol, action, quantity, order_type, limit_price)
    commission = calculate_commission(filled_price * quantity, market_rules)

    context.portfolio.update(symbol, action, quantity, filled_price, commission)

    order_id = generate_order_id()
    trade_record = {
        "order_id": order_id,
        "symbol": symbol,
        "action": action,
        "quantity": quantity,
        "filled_price": filled_price,
        "commission": commission,
        "timestamp": context.current_time.isoformat()
    }
    context.trade_history.append(trade_record)

    return {
        "success": True,
        "order_id": order_id,
        "symbol": symbol,
        "action": action,
        "order_type": order_type,
        "requested_quantity": quantity,
        "filled_quantity": quantity,
        "filled_price": filled_price,
        "commission": commission,
        "timestamp": context.current_time.isoformat(),
        "message": "Order executed successfully"
    }
```


```python
@mcp.tool()
async def get_price(
    symbol: str,
    data_type: Literal["current", "historical"] = "current",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    interval: Literal["1d", "1h", "5m"] = "1d"
) -> dict:
    """

    Args:

    Returns:
        {
            "symbol": "AAPL",
            "current_price": 150.25,
            "change": 2.50,
            "change_percent": 1.69,
            "volume": 45678900,
            "timestamp": "2024-12-28T16:00:00Z",
                {
                    "date": "2024-12-27",
                    "open": 148.00,
                    "high": 151.50,
                    "low": 147.50,
                    "close": 150.25,
                    "volume": 45678900
                },
                ...
            ]
        }

    Note:
    """
    context = get_simulation_context()

    if end_date:
        end_date = min(
            datetime.strptime(end_date, "%Y-%m-%d"),
            context.current_date
        ).strftime("%Y-%m-%d")
    else:
        end_date = context.current_date.strftime("%Y-%m-%d")

    if data_type == "current":
        price_data = await data_provider.get_current_price(
            symbol,
            as_of=context.current_date
        )
        return {
            "symbol": symbol,
            "current_price": price_data["close"],
            "change": price_data["change"],
            "change_percent": price_data["change_percent"],
            "volume": price_data["volume"],
            "timestamp": context.current_time.isoformat()
        }
    else:
        historical = await data_provider.get_historical_prices(
            symbol,
            start_date=start_date,
            end_date=end_date,
            interval=interval
        )

        current = historical[-1] if historical else None

        return {
            "symbol": symbol,
            "current_price": current["close"] if current else None,
            "change": current["change"] if current else None,
            "change_percent": current["change_percent"] if current else None,
            "volume": current["volume"] if current else None,
            "timestamp": context.current_time.isoformat(),
            "historical": historical
        }
```


```python
@mcp.tool()
async def search_information(
    query: str,
    search_type: Literal["news", "analysis", "general"] = "general",
    max_results: int = 5,
    time_range: Optional[str] = None
) -> dict:
    """


    Args:
            - "AAPL earnings report Q4 2024"
            - "Bitcoin price prediction"
            - "Federal Reserve interest rate decision"

    Returns:
        {
            "query": "AAPL earnings report",
            "results": [
                {
                    "title": "Apple Reports Record Q4 Revenue",
                    "snippet": "Apple Inc. announced...",
                    "url": "https://...",
                    "source": "Reuters",
                    "publish_date": "2024-12-27",
                    "relevance_score": 0.95
                },
                ...
            ],
            "total_found": 156,
            "returned": 5
        }

    Note:
    """
    context = get_simulation_context()

    jina_params = {
        "query": query,
        "num_results": max_results,
        "search_type": search_type
    }

    if time_range:
        jina_params["time_range"] = time_range

    raw_results = await jina_client.search(**jina_params)

    filtered_results = []
    for result in raw_results:
        publish_date = parse_date(result.get("publish_date"))
        if publish_date and publish_date <= context.current_date:
            filtered_results.append({
                "title": result["title"],
                "url": result["url"],
                "source": result.get("source", "Unknown"),
                "publish_date": publish_date.strftime("%Y-%m-%d"),
                "relevance_score": result.get("score", 0)
            })

    return {
        "query": query,
        "results": filtered_results[:max_results],
        "total_found": len(raw_results),
        "returned": len(filtered_results[:max_results])
    }
```


```python
@mcp.tool()
async def calculate(expression: str) -> dict:
    """


    Args:


    Returns:
        {
            "expression": "sharpe_ratio([0.1, 0.05, -0.02, 0.08])",
            "result": 1.23,
            "type": "float"
        }

    Examples:
        >>> calculate("100 * 1.05 ** 12")
        {"result": 179.58, ...}

        >>> calculate("sharpe_ratio([0.1, 0.05, -0.02, 0.08])")
        {"result": 1.23, ...}

        >>> calculate("max_drawdown([100, 95, 98, 92, 96])")
        {"result": -0.08, ...}
    """
    try:
        result = safe_eval(
            expression,
            allowed_functions=FINANCIAL_FUNCTIONS,
            allowed_operations=MATH_OPERATIONS
        )

        return {
            "expression": expression,
            "result": result,
            "type": type(result).__name__
        }

    except SyntaxError as e:
        return {
            "expression": expression,
            "error": "SyntaxError",
            "message": f"Invalid expression syntax: {e}"
        }
    except ValueError as e:
        return {
            "expression": expression,
            "error": "ValueError",
            "message": str(e)
        }
    except Exception as e:
        return {
            "expression": expression,
            "error": "CalculationError",
            "message": str(e)
        }

ALLOWED_NAMES = {
    "pi": math.pi,
    "e": math.e,

    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "abs": abs,
    "round": round,

    "mean": lambda x: sum(x) / len(x),
    "std": lambda x: statistics.stdev(x),
    "var": lambda x: statistics.variance(x),
    "median": statistics.median,
    "min": min,
    "max": max,

    "returns": financial.calculate_returns,
    "cumulative_returns": financial.cumulative_returns,
    "sharpe_ratio": financial.sharpe_ratio,
    "max_drawdown": financial.max_drawdown,
    "volatility": financial.volatility,
    "var": financial.value_at_risk,
}

def safe_eval(expression: str, **kwargs) -> Any:
    code = compile(expression, "<string>", "eval")

    for name in code.co_names:
        if name not in ALLOWED_NAMES:
            raise ValueError(f"Name '{name}' is not allowed")

    return eval(code, {"__builtins__": {}}, ALLOWED_NAMES)
```


```python
# start_mcp_services.py

import asyncio
from fastmcp import FastMCP
import uvicorn

SERVICES = [
    {
        "name": "trade",
        "module": "tool_trade",
        "port": 8001,
        "description": "Trade execution service"
    },
    {
        "name": "price",
        "module": "tool_get_price_local",
        "port": 8002,
        "description": "Price data service"
    },
    {
        "name": "search",
        "module": "tool_jina_search",
        "port": 8003,
        "description": "Information search service"
    },
    {
        "name": "math",
        "module": "tool_math",
        "port": 8004,
        "description": "Mathematical calculation service"
    },
    {
        "name": "news",
        "module": "tool_alphavantage_news",
        "port": 8005,
        "description": "News retrieval service"
    },
]

async def start_service(service_config: dict):
    mcp = FastMCP(service_config["name"])

    module = __import__(service_config["module"])

    for tool_func in module.get_tools():
        mcp.add_tool(tool_func)

    config = uvicorn.Config(
        mcp.app,
        host="0.0.0.0",
        port=service_config["port"],
        log_level="info"
    )
    server = uvicorn.Server(config)

    print(f"Starting {service_config['name']} service on port {service_config['port']}")
    await server.serve()

async def start_all_services():
    tasks = [start_service(cfg) for cfg in SERVICES]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    print("Starting MCP Tool Services...")
    print("=" * 50)
    for svc in SERVICES:
        print(f"  - {svc['name']}: port {svc['port']} ({svc['description']})")
    print("=" * 50)

    asyncio.run(start_all_services())
```

---




```python
from abc import ABC, abstractmethod
from datetime import datetime, time
from typing import Optional

class MarketRules(ABC):

    @property
    @abstractmethod
    def market_code(self) -> str:
        pass

    @property
    @abstractmethod
    def currency(self) -> str:
        pass

    @property
    @abstractmethod
    def settlement_type(self) -> str:
        pass

    @property
    @abstractmethod
    def trading_hours(self) -> list:
        pass

    @property
    @abstractmethod
    def commission_rate(self) -> float:
        pass

    @abstractmethod
    def is_trading_day(self, date: datetime) -> bool:
        pass

    @abstractmethod
    def is_trading_hours(self, dt: datetime) -> bool:
        pass

    @abstractmethod
    def can_sell(self, buy_date: datetime, sell_date: datetime) -> bool:
        pass

    @abstractmethod
    def get_lot_size(self, symbol: str) -> int:
        pass
```


```python
class USMarketRules(MarketRules):

    US_HOLIDAYS = [
        "2024-01-01",  # New Year's Day
        "2024-01-15",  # Martin Luther King Jr. Day
        "2024-02-19",  # Presidents' Day
        "2024-03-29",  # Good Friday
        "2024-05-27",  # Memorial Day
        "2024-06-19",  # Juneteenth
        "2024-07-04",  # Independence Day
        "2024-09-02",  # Labor Day
        "2024-11-28",  # Thanksgiving
        "2024-12-25",  # Christmas
    ]

    @property
    def market_code(self) -> str:
        return "US"

    @property
    def currency(self) -> str:
        return "USD"

    @property
    def settlement_type(self) -> str:

    @property
    def trading_hours(self) -> list:
        """
        """
        return [
            {"name": "pre_market", "start": time(4, 0), "end": time(9, 30)},
            {"name": "regular", "start": time(9, 30), "end": time(16, 0)},
            {"name": "after_hours", "start": time(16, 0), "end": time(20, 0)},
        ]

    @property
    def commission_rate(self) -> float:
        return 0.0001  # 0.01%

    def is_trading_day(self, date: datetime) -> bool:
            return False
        if date.strftime("%Y-%m-%d") in self.US_HOLIDAYS:
            return False
        return True

    def is_trading_hours(self, dt: datetime) -> bool:
        if not self.is_trading_day(dt):
            return False

        current_time = dt.time()
        for session in self.trading_hours:
            if session["start"] <= current_time <= session["end"]:
                return True
        return False

    def can_sell(self, buy_date: datetime, sell_date: datetime) -> bool:
        return True

    def get_lot_size(self, symbol: str) -> int:
        return 1
```


```python
class ChinaAShareRules(MarketRules):

    @property
    def market_code(self) -> str:
        return "CN"

    @property
    def currency(self) -> str:
        return "CNY"

    @property
    def settlement_type(self) -> str:

    @property
    def trading_hours(self) -> list:
        """
        """
        return [
            {"name": "morning", "start": time(9, 30), "end": time(11, 30)},
            {"name": "afternoon", "start": time(13, 0), "end": time(15, 0)},
        ]

    @property
    def commission_rate(self) -> float:

    def is_trading_day(self, date: datetime) -> bool:
        if date.weekday() >= 5:
            return False
        return True

    def is_trading_hours(self, dt: datetime) -> bool:
        if not self.is_trading_day(dt):
            return False

        current_time = dt.time()
        for session in self.trading_hours:
            if session["start"] <= current_time <= session["end"]:
                return True
        return False

    def can_sell(self, buy_date: datetime, sell_date: datetime) -> bool:
        return sell_date.date() > buy_date.date()

    def get_lot_size(self, symbol: str) -> int:
        return 100
```


```python
class CryptoMarketRules(MarketRules):

    @property
    def market_code(self) -> str:
        return "CRYPTO"

    @property
    def currency(self) -> str:
        return "USDT"

    @property
    def settlement_type(self) -> str:

    @property
    def trading_hours(self) -> list:
        return [
            {"name": "24h", "start": time(0, 0), "end": time(23, 59, 59)},
        ]

    @property
    def commission_rate(self) -> float:

    def is_trading_day(self, date: datetime) -> bool:
        return True

    def is_trading_hours(self, dt: datetime) -> bool:
        return True

    def can_sell(self, buy_date: datetime, sell_date: datetime) -> bool:
        return True

    def get_lot_size(self, symbol: str) -> int:
        lot_sizes = {
            "BTCUSDT": 0.00001,
            "ETHUSDT": 0.0001,
            "XRPUSDT": 1,
            "SOLUSDT": 0.01,
        }
        return lot_sizes.get(symbol, 0.001)
```


```python
class BaseAgent:

    def __init__(self, market: str = "us", **kwargs):
        self.market = market
        self.market_rules = self._get_market_rules(market)

    def _get_market_rules(self, market: str) -> MarketRules:
        rules_map = {
            "us": USMarketRules(),
            "cn": ChinaAShareRules(),
            "crypto": CryptoMarketRules(),
        }

        if market not in rules_map:
            raise ValueError(f"Unsupported market: {market}")

        return rules_map[market]

    def _build_system_prompt(self, date: str) -> str:
        return f"""
...

## Market Rules
- Market: {self.market_rules.market_code}
- Currency: {self.market_rules.currency}
- Settlement: {self.market_rules.settlement_type}
- Trading Hours: {self._format_trading_hours()}
- Commission Rate: {self.market_rules.commission_rate * 100:.3f}%

## Important Trading Restrictions
{self._get_trading_restrictions()}
...
"""

    def _get_trading_restrictions(self) -> str:
        if self.market == "cn":
            return """- T+1 Settlement: Shares bought today CANNOT be sold until the next trading day
- Lot Size: Must trade in multiples of 100 shares (1 lot)
- Price Limits: ±10% daily price limit (±20% for ChiNext/STAR)"""
        elif self.market == "crypto":
            return """- 24/7 Trading: Market never closes
- High Volatility: Be cautious of large price swings
- No Settlement Restrictions: Can buy and sell instantly"""
        else:  # us
            return """- T+0 Settlement: Can sell shares on the same day you buy them
- Fractional Shares: Can trade partial shares
- Pattern Day Trader Rule: Be aware if account < $25,000"""
```

---





|------|------|------|------|


|------|------|------|------|


|------|------|------|------|


|------|------|


```
┌────────────────────────────────────────────────────────────────────────┐
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │                                                                    │ │
│  │      • GPT-4o                                                      │ │
│  │      • Claude-3.5-Sonnet                                          │ │
│  │      • DeepSeek-V3                                                │ │
│  │      • Gemini-2.0-Flash                                           │ │
│  │      • Qwen-2.5-72B                                               │ │
│  │      • ...                                                         │ │
│  │                                                                    │ │
│  │      • tool_trade (8001)                                          │ │
│  │      • tool_price (8002)                                          │ │
│  │      • tool_search (8003)                                         │ │
│  │      • tool_math (8004)                                           │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                   │                                    │
│                                   ▼                                    │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │                                                                    │ │
│  │  For each trading_day in date_range:                              │ │
│  │      │                                                             │ │
│  │      ▼                                                             │ │
│  │  ┌───────────────────────────────────────────────────────────┐   │ │
│  │  │      agent = create_agent(model, trading_day)              │   │ │
│  │  │      result = agent.run_trading_session()                  │   │ │
│  │  │      save_result(model, trading_day, result)               │   │ │
│  │  └───────────────────────────────────────────────────────────┘   │ │
│  │      │                                                             │ │
│  │      ▼                                                             │ │
│  │  ┌───────────────────────────────────────────────────────────┐   │ │
│  │  │  Update progress:                                          │   │ │
│  │  │  [████████████░░░░░░░░] 60% - Day 180/300                  │   │ │
│  │  └───────────────────────────────────────────────────────────┘   │ │
│  │                                                                    │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                   │                                    │
│                                   ▼                                    │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │                                                                    │ │
│  │      ┌─────┬────────────┬────────┬───────┬─────────┐             │ │
│  │      │Rank │ Model      │ Return │ Sharpe│ MDD     │             │ │
│  │      ├─────┼────────────┼────────┼───────┼─────────┤             │ │
│  │      │ 1   │ Model A    │ +25.3% │ 1.85  │ -8.2%   │             │ │
│  │      │ 2   │ Model B    │ +18.7% │ 1.42  │ -12.5%  │             │ │
│  │      │ ... │ ...        │ ...    │ ...   │ ...     │             │ │
│  │      └─────┴────────────┴────────┴───────┴─────────┘             │ │
│  │                                                                    │ │
│  │                                                                    │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```



|---------|---------|---------|


```python
class DataFilter:
    """

    """

    def __init__(self, simulation_date: datetime):
        self.simulation_date = simulation_date

    def filter_price_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """

        """
        if "date" in data.columns:
            mask = pd.to_datetime(data["date"]) <= self.simulation_date
            return data[mask].copy()
        return data

    def filter_news(self, news_list: List[dict]) -> List[dict]:
        """

        """
        filtered = []
        for news in news_list:
            publish_date = parse_date(news.get("publish_date"))
            if publish_date and publish_date <= self.simulation_date:
                filtered.append(news)
        return filtered

    def validate_agent_decision(self, decision: dict, reasoning: List[dict]) -> bool:
        """

        """
        for step in reasoning:
            if step.get("observation"):
                obs = step["observation"]
                if isinstance(obs, dict):
                    for key, value in obs.items():
                        if "date" in key.lower() and value:
                            ref_date = parse_date(str(value))
                            if ref_date and ref_date > self.simulation_date:
                                self.logger.error(
                                    f"Future information leak detected: "
                                    f"{key}={value} > {self.simulation_date}"
                                )
                                return False
        return True
```


```python
@dataclass
class TradingSessionResult:
    date: str
    model: str
    market: str

    decisions: List[TradeDecision]
    execution_results: List[ExecutionResult]

    reasoning_chain: List[ReasoningStep]
    steps_taken: int
    tokens_used: int

    portfolio_before: PortfolioSnapshot
    portfolio_after: PortfolioSnapshot

    session_return: float
    session_pnl: float

    start_time: datetime
    end_time: datetime
    duration_seconds: float

@dataclass
class BenchmarkResult:
    config: BenchmarkConfig

    model_results: Dict[str, ModelResult]

    leaderboard: List[LeaderboardEntry]

    total_trading_days: int
    total_sessions: int

    generated_at: datetime

# results/{model}/{market}/sessions/{date}.jsonl
```

---




|------|---|

```
AAPL (Apple)        MSFT (Microsoft)    GOOGL (Alphabet)
AMZN (Amazon)       NVDA (NVIDIA)       META (Meta)
TSLA (Tesla)        AMD                 INTC (Intel)
...
```


|------|---|

```
...
```


|------|---|

```
BTC (Bitcoin)       ETH (Ethereum)      XRP (Ripple)
SOL (Solana)        ADA (Cardano)       SUI
LINK (Chainlink)    AVAX (Avalanche)    LTC (Litecoin)
DOT (Polkadot)
```



```yaml
# benchmark_config.yaml

experiment:
  name: "AI-Trader Benchmark 2024"
  version: "1.0"

markets:
  us:
    initial_cash: 10000
    currency: USD
    assets: nasdaq_100
    frequency: daily

  cn:
    initial_cash: 100000
    currency: CNY
    assets: sse_50
    frequency: daily

  crypto:
    initial_cash: 50000
    currency: USDT
    assets: [BTC, ETH, XRP, SOL, ADA, SUI, LINK, AVAX, LTC, DOT]
    frequency: hourly

models:
  - name: gpt-4o
    provider: openai
    temperature: 0.7

  - name: claude-3-5-sonnet
    provider: anthropic
    temperature: 0.7

  - name: deepseek-v3
    provider: deepseek
    temperature: 0.7

  - name: gemini-2.0-flash
    provider: google
    temperature: 0.7

  - name: qwen-2.5-72b
    provider: alibaba
    temperature: 0.7

agent:
  max_steps: 10
  timeout_seconds: 300
  retry_attempts: 3
```


```bash
python main.py \
  --model gpt-4o \
  --market us \
  --start-date 2024-01-01 \
  --end-date 2024-12-31

python main_parallel.py \
  --config configs/benchmark_config.yaml \
  --parallel-models 5 \
  --output-dir results/benchmark_2024
```

---




```

    95 ────┤      ● GPT-4o
           │                  ● Claude-3.5
    90 ────┤
           │          ● Gemini
    85 ────┤
           │               ● DeepSeek
    80 ────┤                      ● Qwen
           │
    75 ────┤
           └─────────────────────────────────

```



|------|---------|---------|-------------|---------|-----------|
| Model A | +15% | +8% | +22% | -9% | ★★★★★ |
| Model B | +28% | -3% | -15% | -35% | ★★☆☆☆ |
| Model C | +8% | +12% | +10% | -7% | ★★★★☆ |
| Model D | +35% | +5% | -8% | -42% | ★☆☆☆☆ |



```

    8 ────────────┤                    ●
                  │               ●
    6 ────────────┤          ●
                  │     ●
    4 ────────────┤  ●
    2 ────────────┤●
                  └───────────────────────────

```



|------------|----------|------|



|-----|------|-----|-----|---------|-----------|
| 1 | - | - | - | - | - |
| 2 | - | - | - | - | - |
| 3 | - | - | - | - | - |



**GPT-4o:**

**Claude-3.5-Sonnet:**

**DeepSeek-V3:**

**Gemini-2.0-Flash:**



```

```


|-----|---------|-----------|

---



|-------|---------|---------|







```python
KNOWN_ISSUES = [
    {
        "id": "ISSUE-001",
        "status": "Workaround implemented",
    },
    {
        "id": "ISSUE-002",
        "status": "Known limitation",
    },
    {
        "id": "ISSUE-003",
        "status": "Under investigation",
    }
]
```

---



   - Llama-3.1-405B
   - Mixtral-8x22B
   - GLM-4











---



|------|------|------|


   - Gao et al. "AI-Trader: Benchmarking Autonomous Agents in Real-Time Financial Markets." arXiv:2512.10971, 2024.

   - Yao et al. "ReAct: Synergizing Reasoning and Acting in Language Models." ICLR 2023.
   - Schick et al. "Toolformer: Language Models Can Teach Themselves to Use Tools." NeurIPS 2023.
   - OpenAI. "GPT-4 Technical Report." 2023.

   - Lo, Andrew W. "The Adaptive Markets Hypothesis." Journal of Portfolio Management, 2004.


|------|------|------|




|------|------|----------|

---


