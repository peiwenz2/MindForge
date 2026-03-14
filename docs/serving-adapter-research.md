# Chat + Model Serving 最优化适配方案研究报告

**研究日期**: 2026-03-14  
**研究范围**: 阿里云百炼 Serving、msg in/out 能力、业界最优适配方案

---

## 1. 阿里云百炼模型-Serving 对应表

### 1.1 支持的开源模型

阿里云百炼（DashScope）支持的开源模型列表：

| 模型系列 | 模型名称 | 区域支持 |
|---------|---------|---------|
| **Qwen3 开源版** | qwen3.5-397b-a17b, qwen3.5-120b-a10b, qwen3.5-27b, qwen3.5-35b-a3b | 中国/美国/国际 |
| **Qwen3 Next** | qwen3-next-80b-a3b-thinking, qwen3-next-80b-a3b-instruct | 全球 |
| **Qwen3 系列** | qwen3-235b-a22b, qwen3-32b, qwen3-30b-a3b, qwen3-14b, qwen3-8b, qwen3-4b, qwen3-1.7b, qwen3-0.6b | 全球 |
| **QwQ 推理** | qwq-32b, qwq-32b-preview | 中国 |
| **Qwen2.5 长文本** | qwen2.5-14b-instruct-1m, qwen2.5-7b-instruct-1m | 中国 |
| **Qwen2.5 系列** | qwen2.5-72b-instruct, qwen2.5-32b-instruct, qwen2.5-14b-instruct, qwen2.5-7b-instruct | 全球 |
| **Qwen2.5 Coder** | qwen2.5-coder-32b-instruct ~ 0.5b-instruct | 中国 |
| **Qwen2.5 Math** | qwen2.5-math-72b-instruct, qwen2.5-math-7b-instruct, qwen2.5-math-1.5b-instruct | 中国 |
| **Qwen2** | qwen2-72b-instruct, qwen2-7b-instruct, qwen2-1.5b-instruct, qwen2-0.5b-instruct | 中国 |
| **Qwen1.5** | qwen1.5-110b-chat ~ 0.5b-chat, codeqwen1.5-7b-chat | 中国 |

### 1.2 商业模型系列

| 模型系列 | 模型名称 | 特点 |
|---------|---------|------|
| **Qwen Max** | qwen3-max, qwen3-max-preview, qwen-max, qwen-max-latest | 旗舰模型 |
| **Qwen Plus** | qwen3.5-plus, qwen-plus, qwen-plus-latest | 性价比优选 |
| **Qwen Flash** | qwen3.5-flash, qwen-flash | 高速推理 |
| **Qwen Turbo** | qwen-turbo, qwen-turbo-latest | 极速响应 |
| **Qwen Coder** | qwen3-coder-plus, qwen3-coder-flash | 代码专用 |
| **Qwen Long** | qwen-long, qwen-long-latest | 长文本支持 |
| **QwQ 推理** | qwq-plus, qwq-plus-latest | 深度推理 |

### 1.3 推理后端与 Feature 支持

**关键发现**:

| Feature | 百炼商业模型 | 百炼开源模型 |
|---------|------------|------------|
| **OpenAI 兼容 API** | ✅ 完全支持 | ✅ 完全支持 |
| **Streaming** | ✅ 支持 | ✅ 支持 |
| **Tool Calling** | ✅ 支持 (qwen-plus/max/turbo) | ⚠️ 部分支持 |
| **Structured Output** | ✅ 支持 | ⚠️ 需测试 |
| **Function Call** | ✅ 支持 | ✅ 支持 |
| **enable_search** | ✅ 联网搜索 | ❌ 不支持 (qwen-long) |

**API 端点**:
- 北京: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- 弗吉尼亚: `https://dashscope-us.aliyuncs.com/compatible-mode/v1`
- 新加坡: `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`

**推理后端推断**:
- 百炼商业模型：阿里自研推理引擎（基于 PAI-EAS）
- 开源模型托管：可能使用 vLLM 或自研后端（官方未明确披露）
- 支持 OpenAI 兼容协议，底层实现对用户透明

---

## 2. msg in/out 技术含义澄清

### 2.1 新定义下的 msg in/out

**用户澄清**: chat 的 msg in/out 指的是对模型 output 的直接输入输出，没有 parser 处理。

在这种定义下：

```
┌─────────────────────────────────────────────────────────────┐
│                    msg in/out 直接 I/O 模式                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   用户请求 ──► API Gateway ──► 模型 Serving ──► 原始输出    │
│      │                                          │          │
│      │              无 Parser 处理               │          │
│      │              无格式转换                   │          │
│      │              无后处理                     │          │
│      └──────────────────────────────────────────┘          │
│                                                             │
│   输入 = 原始 Chat Messages                                  │
│   输出 = 模型生成的原始 token 流                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 msg in/out vs 吞吐量指标对比

| 维度 | msg in/out (新定义) | 吞吐量 (传统定义) |
|------|---------------------|------------------|
| **关注点** | 模型原始 I/O 能力 | 系统处理能力 |
| **测量单位** | tokens/sec (原始) | requests/sec, tokens/sec |
| **影响因素** | 模型架构、GPU 性能 | 并发数、批处理、队列 |
| **包含处理** | ❌ 无额外处理 | ✅ 包含解析、验证、路由 |
| **延迟组成** | 仅推理延迟 | 端到端延迟 |

**核心区别**:
- **msg in/out**: 纯模型推理能力，反映底层引擎效率
- **吞吐量**: 系统级指标，包含 adapter 层开销

### 2.3 直接 I/O 模式对 Adapter 设计的影响

```
┌─────────────────────────────────────────────────────────────┐
│                直接 I/O 模式的 Adapter 设计影响               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 零拷贝传输                                              │
│     - 避免消息序列化/反序列化                                │
│     - 直接传递 token 流                                     │
│     - 减少内存拷贝开销                                       │
│                                                             │
│  2. 协议透明性                                              │
│     - Adapter 不干预消息格式                                │
│     - 保持 OpenAI 协议完整性                                │
│     - 支持透传自定义字段                                     │
│                                                             │
│  3. 流式优先                                                │
│     - 必须支持 streaming-first                              │
│     - 减少首 token 延迟                                     │
│     - 支持 SSE/WebSocket 原生流                             │
│                                                             │
│  4. 错误处理边界                                            │
│     - 模型错误需直接透传                                    │
│     - 不做格式包装                                          │
│     - 保持原始错误信息                                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**设计原则**:
1. **Thin Adapter**: Adapter 层应尽可能薄，只做路由和认证
2. **Pass-through**: 消息内容透传，不做解析修改
3. **Zero-interception**: 不拦截模型输出，直接返回

---

## 3. 业界最优适配方案对比

### 3.1 方案概览

| 方案 | 定位 | 核心优势 | 适用场景 |
|------|------|---------|---------|
| **LiteLLM** | AI Gateway | 100+ LLM 支持、统一 API | 企业级多模型路由 |
| **OpenRouter** | Model Aggregator | 价格透明、模型丰富 | 快速原型开发 |
| **Together AI** | Inference Platform | 开源模型专属、高性能 | 开源模型生产部署 |
| **vLLM/SGLang Native** | 专用引擎 | 极致性能、深度优化 | 单一引擎场景 |
| **自建 Adapter** | 定制方案 | 完全控制、灵活适配 | 特殊需求场景 |

### 3.2 LiteLLM 详细分析

**架构特点**:
```
┌─────────────────────────────────────────────────────────────┐
│                      LiteLLM 架构                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   客户端 ──► OpenAI SDK ──► LiteLLM Proxy                   │
│                                │                            │
│                    ┌───────────┼───────────┐               │
│                    ▼           ▼           ▼               │
│              ┌─────────┐ ┌─────────┐ ┌─────────┐          │
│              │ OpenAI  │ │ Bedrock │ │ DashScope│ ...      │
│              └─────────┘ └─────────┘ └─────────┘          │
│                                                             │
│  核心能力:                                                  │
│  • 100+ Provider 支持 (含 DashScope/阿里云百炼)             │
│  • 统一 OpenAI 格式 API                                     │
│  • 负载均衡 (simple-shuffle, least-busy, latency-based)    │
│  • 自动 Fallback & Retry                                   │
│  • 成本追踪 & 限流                                          │
│  • 虚拟密钥管理                                             │
│                                                             │
│  性能指标: P95 延迟 8ms @ 1k RPS                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**路由策略**:
| 策略 | 描述 | 适用场景 |
|------|------|---------|
| `simple-shuffle` | 基于 RPM/TPM 权重随机 | 生产推荐 |
| `least-busy` | 选择最空闲部署 | 高并发场景 |
| `latency-based` | 选择最低延迟 | 延迟敏感 |
| `usage-based` | 基于使用率均衡 | 成本优化 |
| `cost-based` | 选择最低成本 | 成本优先 |

**DashScope 支持**:
- ✅ chat/completions
- ✅ embeddings
- ✅ 自定义 api_base

### 3.3 Together AI 分析

**核心优势**:
- OpenAI API 完全兼容，只需更换 `base_url`
- 专注开源模型，性能优化深入
- 支持 Vision、Function Calling、Structured Output
- 提供图像生成、语音合成等多模态能力

**模型示例**:
- Llama 系列 (Llama-4-Maverick)
- Qwen 系列 (Qwen3-Next-80B)
- GLM 系列 (GLM-4.5-Air)
- DeepSeek 等开源模型

### 3.4 OpenRouter 分析

**特点**:
- 聚合多个 Provider，提供统一入口
- 价格透明，自动选择最优价格
- 支持模型发现和比较
- 适合快速原型开发

### 3.5 vLLM / SGLang 原生方案

| 引擎 | 特点 | msg in/out 支持 |
|------|------|-----------------|
| **vLLM** | PagedAttention, 连续批处理 | ✅ 原生支持 |
| **SGLang** | Structured Generation, 高效推理 | ✅ 原生支持 |

**关键特性**:
- 两者都支持 OpenAI 兼容 API
- 直接暴露模型输出，无中间处理层
- msg in/out 性能最优

---

## 4. 推荐方案及理由

### 4.1 推荐方案：LiteLLM + 自定义 Thin Adapter

**架构设计**:

```
┌─────────────────────────────────────────────────────────────┐
│                   推荐架构：多层分离设计                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐                                            │
│  │   客户端    │                                            │
│  └──────┬──────┘                                            │
│         │ OpenAI SDK                                        │
│         ▼                                                   │
│  ┌─────────────────────────────────────────────────┐       │
│  │           LiteLLM Proxy (AI Gateway)             │       │
│  │  • 统一认证 (Virtual Keys)                        │       │
│  │  • 负载均衡 & Fallback                           │       │
│  │  • 成本追踪 & 限流                               │       │
│  │  • 多 Provider 路由                              │       │
│  └──────────────────────┬──────────────────────────┘       │
│                         │                                   │
│         ┌───────────────┼───────────────┐                  │
│         ▼               ▼               ▼                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐           │
│  │  DashScope │  │  Together  │  │   自建vLLM  │           │
│  │  (阿里云)   │  │    AI     │  │   SGLang   │           │
│  └────────────┘  └────────────┘  └────────────┘           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 方案优势

| 维度 | 优势说明 |
|------|---------|
| **msg in/out** | LiteLLM 透传模式，保持原始输出 |
| **自动化** | 100+ Provider 自动适配，无需手动编码 |
| **可扩展** | 新 Provider 只需配置，无需开发 |
| **可靠性** | 内置 Fallback、Retry、Cooldown |
| **可观测** | 日志、监控、成本追踪开箱即用 |
| **合规性** | 支持数据隔离、区域路由 |

### 4.3 实施步骤

```yaml
# config.yaml 示例
model_list:
  - model_name: qwen-plus
    litellm_params:
      model: dashscope/qwen-plus
      api_key: os.environ/DASHSCOPE_API_KEY
      api_base: https://dashscope.aliyuncs.com/compatible-mode/v1
    model_info:
      description: "阿里云百炼 Qwen Plus"
      
  - model_name: qwen-plus  # 负载均衡
    litellm_params:
      model: dashscope/qwen-plus-us
      api_key: os.environ/DASHSCOPE_API_KEY_US
      api_base: https://dashscope-us.aliyuncs.com/compatible-mode/v1
      
  - model_name: qwen-opensource
    litellm_params:
      model: openai/qwen2.5-72b-instruct
      api_base: https://api.together.xyz/v1
      api_key: os.environ/TOGETHER_API_KEY

router_settings:
  routing_strategy: simple-shuffle
  num_retries: 3
  timeout: 30

general_settings:
  master_key: os.environ/MASTER_KEY
```

### 4.4 对于 msg in/out 的特殊配置

```python
from litellm import Router

# 启用透传模式，最小化 adapter 干预
router = Router(
    model_list=model_list,
    routing_strategy="simple-shuffle",
    # 关键配置：保持原始输出
    default_litellm_params={
        "drop_params": False,  # 不丢弃任何参数
    },
    # 启用详细日志便于调试
    set_verbose=True
)

# 直接调用，获取原始响应
response = await router.acompletion(
    model="qwen-plus",
    messages=[{"role": "user", "content": "Hello"}],
    stream=True  # 流式获取原始 token 流
)
```

---

## 5. 结论

### 5.1 核心发现

1. **阿里云百炼**: 提供完整的 OpenAI 兼容 API，支持主流开源模型和商业模型，底层推理引擎对用户透明

2. **msg in/out 新定义**: 指模型原始输入输出，无 parser 处理，要求 adapter 层尽可能薄，实现透传

3. **最优方案**: LiteLLM 作为统一 AI Gateway，配合多 Provider 策略，实现自动化适配和高可用

### 5.2 关键建议

| 建议 | 理由 |
|------|------|
| 采用 LiteLLM Proxy | 开箱即用的多 Provider 支持，含阿里云百炼 |
| 配置多区域部署 | 利用阿里云北京/弗吉尼亚/新加坡多区域实现容灾 |
| 启用 streaming-first | 最小化首 token 延迟，符合 msg in/out 定义 |
| 设置 Fallback 策略 | 自动在 DashScope、Together AI 之间切换 |
| 监控原始延迟 | 关注 msg in/out 级延迟，而非端到端延迟 |

### 5.3 后续行动

1. **短期**: 部署 LiteLLM Proxy，配置 DashScope + Together AI 双 Provider
2. **中期**: 建立延迟监控体系，优化 msg in/out 性能
3. **长期**: 根据业务需求，考虑自建 Thin Adapter 层进一步优化

---

*报告完成于 2026-03-14*