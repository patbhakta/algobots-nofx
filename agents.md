























- exchange skill

























































































































- `manage_trader`
- `manage_exchange_config`
- `manage_model_config`
- `manage_strategy`
- `diagnose_trader_start_failure`


- `get_model_list_then_find_enabled_one`
- `read_exchange_then_patch_field`
- `generic_api_request`





























- `docs/agent-skills/diagnostic-skills.zh-CN.md`







- `manage_trader`
- `manage_exchange_config`
- `manage_model_config`
- `manage_strategy`
- `execute_trade`
- `get_positions`
- `get_balance`
- `get_trade_history`
- `search_stock`



















- `trader_management`
- `exchange_management`
- `model_management`
- `strategy_management`


- `manage_trader`
- `manage_exchange_config`
- `manage_model_config`
- `manage_strategy`




- `action`
- `target_ref`
- `slots`
- `needs_confirmation`


```json
{
  "skill": "exchange_management",
  "action": "update",
  "target_ref": {
    "id": "optional",
    "alias": "optional"
  },
  "slots": {
    "passphrase": "xxx"
  },
  "needs_confirmation": false
}
```



- `trader_management`
  - `create`
  - `update`
  - `delete`
  - `start`
  - `stop`
  - `query`
- `exchange_management`
  - `create`
  - `update`
  - `delete`
  - `query`
- `model_management`
  - `create`
  - `update`
  - `delete`
  - `query`
- `strategy_management`
  - `create`
  - `update`
  - `delete`
  - `activate`
  - `duplicate`
  - `query`








- `exchange_management.create`
- `exchange_management.update`
- `trader_management.create`







- `model_diagnosis`
- `exchange_diagnosis`
- `trader_diagnosis`
- `order_execution_diagnosis`
- `strategy_diagnosis`
- `balance_position_diagnosis`













- `get_preferences`
- `manage_preferences`
- `get_exchange_configs`
- `manage_exchange_config`
- `get_model_configs`
- `manage_model_config`
- `get_strategies`
- `manage_strategy`
- `manage_trader`
- `search_stock`
- `execute_trade`
- `get_positions`
- `get_balance`
- `get_market_price`
- `get_trade_history`




- `manage_exchange_config`
- `manage_model_config`
- `manage_strategy`
- `manage_trader`
- `execute_trade`







- `get_exchange_configs`
- `get_model_configs`
- `get_strategies`
- `get_positions`
- `get_balance`
- `get_market_price`
- `get_trade_history`
- `search_stock`







- `get_preferences`
- `manage_preferences`







#### 1. `manage_trader`


- `trader_management`
- `trader_diagnosis`



#### 2. `manage_exchange_config`


- `exchange_management`
- `exchange_diagnosis`



#### 3. `manage_model_config`


- `model_management`
- `model_diagnosis`



#### 4. `manage_strategy`


- `strategy_management`
- `strategy_diagnosis`





1. `create_trader`
2. `trader_management`
3. `exchange_management`
4. `model_management`
5. `exchange_diagnosis`
6. `model_diagnosis`
7. `trader_diagnosis`






