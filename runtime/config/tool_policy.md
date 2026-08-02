# Tool Policy

## Tool Selection Criteria
1. **Authority**: Prefer official AWS/Azure/GCP documentation
2. **Recency**: Prioritize sources from the last 12 months
3. **Completeness**: Ensure all aspects of the task are covered
4. **Actionability**: Provide step-by-step instructions

## Search Strategy
- Use Tavily for general web search
- Use web_read for detailed page content
- If web_read returns browser_required, use the Patchright-backed Browser

## Memory Management
- Store important patterns in archival memory
- Update core memory blocks when context changes
- Compact session history when approaching limits
- Maintain separate memories for different domains

## Error Handling
- Retry failed operations with exponential backoff
- Log errors with context for debugging
- Gracefully degrade when optional services fail
- Provide clear error messages to users

## Performance Optimization
- Cache frequently accessed data
- Use async operations where possible
- Batch API calls when available
- Monitor and optimize memory usage
