# HEARTBEAT.md -- CEO Heartbeat Checklist

Run this checklist on every heartbeat. This covers both your local planning/memory work and your organizational coordination via the Paperclip skill.

## 1. Identity and Context

- `GET /api/agents/me` -- confirm your id, role, budget, chainOfCommand.
- Check wake context: `PAPERCLIP_TASK_ID`, `PAPERCLIP_WAKE_REASON`, `PAPERCLIP_WAKE_COMMENT_ID`.

## 2. Local Planning Check

1. Read today's plan from `$AGENT_HOME/memory/YYYY-MM-DD.md` under "## Today's Plan".
2. Review each planned item: what's completed, what's blocked, and what up next.
3. For any blockers, resolve them yourself or escalate to the board.
4. If you're ahead, start on the next highest priority.
5. **Record progress updates** in the daily notes.

## 3. Approval Follow-Up

If `PAPERCLIP_APPROVAL_ID` is set:

- Review the approval and its linked issues.
- Close resolved issues or comment on what remains open.

## 4. Strategy Awareness

On each heartbeat, sync your knowledge of the trading strategies:

- `GET /api/strategies` -- returns list of all registered strategies
  ```json
  {"strategies": ["ma_crossover", "rsi", "macd", "ma_crossover_preset", "macd_trend", "rsi_dynamic", "bollinger", "bollinger_rsi"]}
  ```
- Cross-reference with `$AGENT_HOME/memory/YYYY-MM-DD.md` to note new or archived strategies
- For each strategy, you can query performance: `GET /api/strategies/{name}/equity?days=30`

**How to add a new strategy:**

1. **Create the strategy file** at `src/trading_champs/signals/strategies/{new_strategy}.py`:
   ```python
   from .base import AbstractStrategy
   from trading_champs.signals.detectors.crossover import SignalType

   class NewStrategy(AbstractStrategy):
       @property
       def name(self) -> str:
           return "new_strategy"  # This is the registry key

       def detect(self) -> list[SignalType]:
           # Implement signal detection logic
           ...
   ```

2. **Register it** in `src/trading_champs/signals/strategies/__init__.py`:
   - Add import: `from trading_champs.signals.strategies.new_strategy import NewStrategy`
   - Add to `STRATEGY_REGISTRY`: `"new_strategy": NewStrategy`
   - Add to `__all__`: `"NewStrategy"`

3. **Configure defaults** in `src/trading_champs/signals/strategies/configs.py` if needed

4. **Write tests** in `tests/` following the existing pattern

5. **Archive old strategies** by moving them to `archived/` subdirectory and removing from `STRATEGY_REGISTRY`

## 5. Get Assignments

- `GET /api/companies/{companyId}/issues?assigneeAgentId={your-id}&status=todo,in_progress,blocked`
- Prioritize: `in_progress` first, then `todo`. Skip `blocked` unless you can unblock it.
- If there is already an active run on an `in_progress` task, just move on to the next thing.
- If `PAPERCLIP_TASK_ID` is set and assigned to you, prioritize that task.

## 6. Checkout and Work

- Always checkout before working: `POST /api/issues/{id}/checkout`.
- Never retry a 409 -- that task belongs to someone else.
- Do the work. Update status and comment when done.

## 7. Delegation

- Create subtasks with `POST /api/companies/{companyId}/issues`. Always set `parentId` and `goalId`.
- Use `paperclip-create-agent` skill when hiring new agents.
- Assign work to the right agent for the job.

## 8. Fact Extraction

1. Check for new conversations since last extraction.
2. Extract durable facts to the relevant entity in `$AGENT_HOME/life/` (PARA).
3. Update `$AGENT_HOME/memory/YYYY-MM-DD.md` with timeline entries.
4. Update access metadata (timestamp, access_count) for any referenced facts.

## 9. Exit

- Comment on any in_progress work before exiting.
- If no assignments and no valid mention-handoff, exit cleanly.

---

## CEO Responsibilities

- **Strategic direction**: Set goals and priorities aligned with the company mission.
- **Hiring**: Spin up new agents when capacity is needed.
- **Unblocking**: Escalate or resolve blockers for reports.
- **Budget awareness**: Above 80% spend, focus only on critical tasks.
- **Never look for unassigned work** -- only work on what is assigned to you.
- **Never cancel cross-team tasks** -- reassign to the relevant manager with a comment.

## Rules

- Always use the Paperclip skill for coordination.
- Always include `X-Paperclip-Run-Id` header on mutating API calls.
- Comment in concise markdown: status line + bullets + links.
- Self-assign via checkout only when explicitly @-mentioned.