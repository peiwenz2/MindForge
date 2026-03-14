# Research State - Chat + Model Serving Architecture

**Status**: 🔄 In Progress
**Started**: 2026-03-14
**Cycle**: 2 (Completed)

## Cycle 2 Findings

### 1. Alibaba Cloud Bailian Model Survey

**Open Source Models**: Qwen3 (397B~0.6B), Qwen2.5 (72B~7B + 1M long context), QwQ, Qwen2.5 Coder/Math

**Commercial Models**: Qwen Max/Plus/Flash/Turbo tiered产品线

**Key Finding**: Bailian provides full OpenAI-compatible API, but underlying serving backend (vLLM/SGLang/self-built) is NOT disclosed.

### 2. msg in/out Redefined

**User Clarification**: Direct model I/O without parser processing.

**Implications for Adapter Design**:
- **Thin Adapter**: Minimal intervention, pass-through mode
- **Zero-copy**: Avoid serialization/deserialization
- **Streaming-first**: Minimize TTFT, native SSE/WebSocket
- **Error transparency**: Pass through raw model errors

### 3. Industry Best Practice: LiteLLM + Multi-Provider

**Recommended Architecture**:
```
Client → LiteLLM Proxy → [DashScope (Bailian), Together AI, Self-hosted vLLM/SGLang]
```

**Why LiteLLM**:
- ✅ 100+ Provider support (including DashScope)
- ✅ Built-in Fallback, Retry, Load Balancing
- ✅ P95 latency 8ms @ 1k RPS
- ✅ Pass-through mode for msg in/out
- ✅ Cost tracking, rate limiting, virtual keys

**Routing Strategies**: simple-shuffle (prod), least-busy, latency-based, cost-based

## Completed

- [x] vLLM vs SGLang architecture comparison (Cycle 1)
- [x] Alibaba Cloud Bailian model-serving survey (Cycle 2)
- [x] msg in/out definition clarification (Cycle 2)
- [x] Industry best practices research - LiteLLM (Cycle 2)
- [x] Recommended architecture design (Cycle 2)

## Next Steps (Cycle 3)

- [ ] Deploy LiteLLM Proxy with DashScope + Together AI
- [ ] Implement benchmark for msg in/out latency
- [ ] Production deployment guide
- [ ] Thin Adapter code implementation (if needed)

## Documents

- `docs/2026-03-14-chat-model-serving-architecture.md` (Cycle 1)
- `docs/serving-adapter-research.md` (Cycle 2)

---

**Last Updated**: 2026-03-14 23:17 GMT+8
