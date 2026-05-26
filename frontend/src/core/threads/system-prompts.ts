export const SYSTEM_SESSION_CONTINUE_PROMPT = `[system: session context compressed — continue executing]
你的上下文已被压缩。执行规则：
1. 查看 <continue_context> 或 <task_state_checkpoint> 中的任务状态
2. 继续执行 pending_steps 中的下一个待办项
3. 不要重复已完成的步骤（completed_steps）
4. 不要询问用户已经提供过的信息
5. 直接从上次中断的位置继续工作
6. 如果有 in_progress 的任务，立即恢复执行`;

