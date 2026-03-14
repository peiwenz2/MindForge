# Chat + Model Serving 分离式部署架构设计文档

**版本**: v1.0  
**日期**: 2026-03-14  
**作者**: Architecture Research Agent

---

## 目录

1. [背景与问题](#1-背景与问题)
2. [vLLM vs SGLang 架构对比分析](#2-vllm-vs-sglang-架构对比分析)
3. [Chat 层适配方案设计](#3-chat-层适配方案设计)
4. [Feature 支持对比表](#4-feature-支持对比表)
5. [评估标准与打分体系](#5-评估标准与打分体系)
6. [多 Serving 协作架构](#6-多-serving-协作架构)
7. [实施建议](#7-实施建议)

---

## 1. 背景与问题

### 1.1 现状

在 LLM 服务部署中，vLLM 和 SGLang 是两大主流开源推理引擎：

- **vLLM**: UC Berkeley 起源，社区驱动，以 PagedAttention 技术著称
- **SGLang**: LMSYS 开发，以 RadixAttention 和零开销调度器为特色

两者对不同模型的 feature 支持能力存在差异，单一 serving 无法完美支撑所有开源模型。

### 1.2 核心问题

1. **适配层设计**: 如何让 chat 层透明适配不同 model serving？
2. **Feature 兼容**: 如何针对不同 serving 支持所有特性？
3. **多引擎协作**: 如何让 vLLM 和 SGLang 配合支撑所有开源模型？
4. **评估标准**: 如何断定哪个 serving 更优？

---

## 2. vLLM vs SGLang 架构对比分析

### 2.1 架构图（文字描述）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          vLLM Architecture                               │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                  │
│  │ API Server  │───▶│ Scheduler   │───▶│ Worker      │                  │
│  │ (OpenAI)    │    │ (Continuous │    │ Manager     │                  │
│  │             │    │  Batching)  │    │             │                  │
│  └─────────────┘    └─────────────┘    └─────────────┘                  │
│         │                  │                  │                          │
│         ▼                  ▼                  ▼                          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                  │
│  │ Model       │    │ Block       │    │ GPU         │                  │
│  │ Runner      │    │ Manager     │    │ Executors   │                  │
│  │             │    │ (PagedAttn) │    │             │                  │
│  └─────────────┘    └─────────────┘    └─────────────┘                  │
│                                                                          │
│  Key: PagedAttention + Continuous Batching + CUDA Graph                 │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                          SGLang Architecture                             │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                  │
│  │ API Server  │───▶│ Zero-Overhead│───▶│ Tokenizer   │                  │
│  │ (OpenAI)    │    │ Scheduler   │    │ Manager     │                  │
│  │             │    │ (CPU-based) │    │             │                  │
│  └─────────────┘    └─────────────┘    └─────────────┘                  │
│         │                  │                  │                          │
│         ▼                  ▼                  ▼                          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                  │
│  │ RadixAttn   │    │ KV Cache    │    │ Model       │                  │
│  │ (Prefix     │    │ Manager     │    │ Workers     │                  │
│  │  Caching)   │    │             │    │             │                  │
│  └─────────────┘    └─────────────┘    └─────────────┘                  │
│                                                                          │
│  Key: RadixAttention + Zero-Overhead Scheduler + PD Disaggregation      │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 核心技术差异

| 维度 | vLLM | SGLang |
|------|------|--------|
| **注意力机制** | PagedAttention (分页式KV缓存) | RadixAttention (基数树前缀缓存) |
| **调度器** | Continuous Batching | Zero-Overhead CPU Scheduler |
| **前缀缓存** | Prefix Caching (块级) | RadixAttention (树形共享) |
| **分布式** | TP/PP/DP/EP | TP/PP/DP/EP + PD Disaggregation |
| **量化支持** | GPTQ, AWQ, INT4/8, FP8 | FP4/FP8/INT4/AWQ/GPTQ |
| **结构化输出** | 支持 (via guided decoding) | 支持 (XGrammar/Outlines/llguidance) |
| **推测解码** | 支持 | 支持 |
| **多模态** | 支持 | 支持更广泛 (包括 Diffusion) |

### 2.3 API 兼容性

两者都提供 **OpenAI-Compatible API**：

```
共同支持的 API:
├── /v1/completions
├── /v1/chat/completions
├── /v1/embeddings
├── /v1/models
└── Tokenizer API (/tokenize, /detokenize)

vLLM 特有 API:
├── /v1/responses
├── /pooling
├── /classify
├── /score
└── /rerank (Jina/Cohere 兼容)

SGLang 特有 API:
├── /generate (Native API)
├── Native SGLang Runtime API
└── 更多 Diffusion 相关 API
```

---

## 3. Chat 层适配方案设计

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Chat Layer (上层应用)                          │
│                    Chat UI / WebSocket / HTTP API                        │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Model Serving Adapter Layer                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    Feature Detection & Routing                   │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │    │
│  │  │ Model        │  │ Feature      │  │ Load         │          │    │
│  │  │ Registry     │  │ Capability   │  │ Balancer     │          │    │
│  │  │              │  │ Matrix       │  │              │          │    │
│  │  └──────────────┘  └──────────────┘  └──────────────┘          │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    Serving Backend Adapters                      │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │    │
│  │  │ vLLM         │  │ SGLang       │  │ Future       │          │    │
│  │  │ Adapter      │  │ Adapter      │  │ Adapters     │          │    │
│  │  │              │  │              │  │ (TRT-LLM,etc)│          │    │
│  │  └──────────────┘  └──────────────┘  └──────────────┘          │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    Unified Feature Interface                     │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │    │
│  │  │ Completion   │  │ Structured   │  │ Multimodal   │          │    │
│  │  │ API          │  │ Output       │  │ Input        │          │    │
│  │  └──────────────┘  └──────────────┘  └──────────────┘          │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                      ▼
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│   vLLM Server       │  │   SGLang Server     │  │   Other Serving     │
│   :8000             │  │   :8001             │  │   :8002...          │
└─────────────────────┘  └─────────────────────┘  └─────────────────────┘
```

### 3.2 Adapter 接口设计

```python
# ============================================================
# Core Adapter Interface (Python Pseudocode)
# ============================================================

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
from enum import Enum

class ServingBackend(Enum):
    VLLM = "vllm"
    SGLANG = "sglang"
    TRT_LLM = "trt_llm"
    AUTO = "auto"

@dataclass
class FeatureCapability:
    """描述单个特性的支持能力"""
    feature_name: str
    supported: bool
    backend_specific_params: Dict[str, Any]  # 后端特有参数映射
    fallback_available: bool
    fallback_method: Optional[str]

@dataclass
class ModelInfo:
    """模型信息"""
    model_id: str
    model_type: str  # "text", "multimodal", "embedding", "diffusion"
    context_length: int
    supported_features: List[str]

class ServingAdapter(ABC):
    """Serving 后端适配器基类"""
    
    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        pass
    
    @abstractmethod
    async def get_model_info(self) -> ModelInfo:
        """获取模型信息"""
        pass
    
    @abstractmethod
    async def get_capabilities(self) -> Dict[str, FeatureCapability]:
        """获取特性支持矩阵"""
        pass
    
    @abstractmethod
    async def chat_completion(
        self,
        messages: List[Dict],
        model: str,
        temperature: float = 1.0,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict] = None,
        tools: Optional[List[Dict]] = None,
        **kwargs
    ) -> Dict:
        """
        统一的 Chat Completion 接口
        - response_format: 结构化输出格式
        - tools: Function calling 工具定义
        """
        pass
    
    @abstractmethod
    async def structured_output(
        self,
        messages: List[Dict],
        schema: Dict,  # JSON Schema
        backend: str = "auto",  # "xgrammar", "outlines", "llguidance"
        **kwargs
    ) -> Dict:
        """
        结构化输出 - 统一接口
        自动映射到各后端的实现方式
        """
        pass
    
    @abstractmethod
    async def multimodal_completion(
        self,
        messages: List[Dict],
        images: Optional[List[str]] = None,
        audio: Optional[List[str]] = None,
        video: Optional[List[str]] = None,
        **kwargs
    ) -> Dict:
        """
        多模态输入处理
        """
        pass
    
    @abstractmethod
    def translate_params(self, params: Dict) -> Dict:
        """
        参数翻译 - 将统一参数转换为后端特有参数
        
        Example:
            Input: {"response_format": {"type": "json_schema", ...}}
            vLLM Output: {"guided_json": ...}
            SGLang Output: {"json_schema": ...}
        """
        pass


class vLLMAdapter(ServingAdapter):
    """vLLM 适配器实现"""
    
    # vLLM 特有的参数映射
    PARAM_MAPPING = {
        "response_format": {
            "json_object": {"guided_json": None},
            "json_schema": {"guided_json": "$schema"},
            "regex": {"guided_regex": "$pattern"},
        },
        "top_k": "top_k",  # vLLM 支持 top_k
        "min_p": "min_p",
        "repetition_penalty": "repetition_penalty",
    }
    
    async def chat_completion(self, messages, model, **kwargs):
        # 转换参数
        vllm_params = self.translate_params(kwargs)
        # 调用 vLLM OpenAI API
        return await self._call_openai_api(messages, model, **vllm_params)
    
    def translate_params(self, params: Dict) -> Dict:
        result = {}
        for key, value in params.items():
            if key in self.PARAM_MAPPING:
                mapping = self.PARAM_MAPPING[key]
                if isinstance(mapping, dict):
                    # 复杂映射
                    pass
                else:
                    result[mapping] = value
            else:
                result[key] = value
        return result


class SGLangAdapter(ServingAdapter):
    """SGLang 适配器实现"""
    
    # SGLang 特有的参数映射
    PARAM_MAPPING = {
        "response_format": {
            "json_schema": {"json_schema": "$schema"},
            "ebnf": {"ebnf": "$grammar"},
            "regex": {"regex": "$pattern"},
            "structural_tag": {"structural_tag": "$config"},
        },
    }
    
    async def structured_output(self, messages, schema, backend="xgrammar", **kwargs):
        # SGLang 支持多种 grammar backend
        if backend != "xgrammar":
            # 需要在启动时指定 --grammar-backend
            pass
        return await self.chat_completion(
            messages, 
            response_format={"type": "json_schema", "json_schema": schema},
            **kwargs
        )
```

### 3.3 特性检测与路由

```python
# ============================================================
# Feature Detection & Routing Logic
# ============================================================

class FeatureRouter:
    """基于特性支持度的智能路由"""
    
    def __init__(self, adapters: Dict[ServingBackend, ServingAdapter]):
        self.adapters = adapters
        self.capability_cache: Dict[str, Dict[str, FeatureCapability]] = {}
    
    async def initialize(self):
        """初始化时收集各后端的能力矩阵"""
        for backend, adapter in self.adapters.items():
            self.capability_cache[backend.value] = await adapter.get_capabilities()
    
    def select_backend(
        self, 
        model: str,
        required_features: List[str],
        preference: ServingBackend = ServingBackend.AUTO
    ) -> ServingBackend:
        """
        选择最佳后端
        
        策略:
        1. 如果指定了 preference 且满足特性需求，使用指定后端
        2. 否则，选择支持所有必需特性的后端
        3. 多个后端都满足时，选择评分更高的
        """
        
        if preference != ServingBackend.AUTO:
            if self._check_features(preference, required_features):
                return preference
        
        candidates = []
        for backend in [ServingBackend.SGLANG, ServingBackend.VLLM]:
            if self._check_features(backend, required_features):
                score = self._calculate_score(backend, model, required_features)
                candidates.append((backend, score))
        
        if not candidates:
            raise UnsupportedFeatureError(
                f"No backend supports all features: {required_features}"
            )
        
        # 返回评分最高的后端
        return max(candidates, key=lambda x: x[1])[0]
    
    def _check_features(self, backend: ServingBackend, features: List[str]) -> bool:
        """检查后端是否支持所有特性"""
        caps = self.capability_cache.get(backend.value, {})
        for f in features:
            if f not in caps or not caps[f].supported:
                # 检查是否有 fallback
                if f in caps and caps[f].fallback_available:
                    continue
                return False
        return True
    
    def _calculate_score(
        self, 
        backend: ServingBackend, 
        model: str, 
        features: List[str]
    ) -> float:
        """
        计算后端评分
        
        评分因素:
        - 原生支持 vs fallback
        - 历史性能数据
        - 模型优化程度
        """
        score = 0.0
        caps = self.capability_cache.get(backend.value, {})
        
        for f in features:
            if f in caps:
                if caps[f].supported:
                    score += 1.0  # 原生支持
                elif caps[f].fallback_available:
                    score += 0.5  # 有 fallback
        
        # 加上模型特定优化加分
        score += self._get_model_bonus(backend, model)
        
        return score
    
    def _get_model_bonus(self, backend: ServingBackend, model: str) -> float:
        """模型特定优化加分"""
        # DeepSeek 系列在 SGLang 有特殊优化
        if "deepseek" in model.lower():
            if backend == ServingBackend.SGLANG:
                return 0.5
        
        # 某些模型在 vLLM 有更好的支持
        # ... 其他模型特定规则
        
        return 0.0
```

### 3.4 统一请求处理流程

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Request Processing Flow                          │
└─────────────────────────────────────────────────────────────────────────┘

1. 接收请求
   │
   ▼
2. 解析所需特性
   ├── response_format? → 需要 structured_output
   ├── images/audio? → 需要 multimodal_input
   ├── tools? → 需要 function_calling
   └── 其他特殊参数
   │
   ▼
3. 查询 Model Registry
   ├── 模型是否已加载?
   ├── 在哪个后端?
   └── 支持哪些特性?
   │
   ▼
4. 选择后端 (Feature Router)
   ├── 评估各后端能力
   ├── 选择最优后端
   └── 如无合适后端，返回错误
   │
   ▼
5. 参数转换 (Adapter)
   ├── 统一参数 → 后端特有参数
   ├── 处理不支持的参数
   └── 设置默认值
   │
   ▼
6. 发送请求到 Serving
   ├── HTTP/gRPC 调用
   └── 流式响应处理
   │
   ▼
7. 响应标准化
   ├── 统一响应格式
   └── 错误处理
   │
   ▼
8. 返回给上层应用
```

---

## 4. Feature 支持对比表

### 4.1 核心特性对比

| 特性 | vLLM | SGLang | 统一接口设计 |
|------|------|--------|-------------|
| **基础推理** |
| Chat Completion | ✅ 完整支持 | ✅ 完整支持 | `chat_completion()` |
| Streaming | ✅ SSE | ✅ SSE | `stream=True` |
| Batch Inference | ✅ | ✅ | 批量请求 |
| **采样参数** |
| temperature | ✅ | ✅ | 统一 |
| top_p | ✅ | ✅ | 统一 |
| top_k | ✅ | ✅ | 统一 |
| min_p | ✅ | ✅ | 统一 |
| repetition_penalty | ✅ | ✅ | 统一 |
| beam_search | ✅ | ✅ | `use_beam_search=True` |
| **结构化输出** |
| JSON Schema | ✅ guided_json | ✅ XGrammar | `response_format.type="json_schema"` |
| Regex | ✅ guided_regex | ✅ | `extra_body={"regex": ...}` |
| EBNF | ❌ | ✅ | `extra_body={"ebnf": ...}` |
| Structural Tag | ❌ | ✅ | `response_format.type="structural_tag"` |
| Grammar Backend | 内置 | XGrammar/Outlines/llguidance | 可配置 |
| **多模态** |
| 图像输入 | ✅ | ✅ | `messages[].content[].type="image_url"` |
| 音频输入 | ✅ | ✅ | `messages[].content[].type="input_audio"` |
| 视频输入 | ⚠️ 有限 | ✅ | 依赖模型 |
| 多图像 | ✅ | ✅ | 多 content 块 |
| **高级特性** |
| Speculative Decoding | ✅ | ✅ | 后端配置 |
| Prefix Caching | ✅ Block-level | ✅ RadixAttention | 自动启用 |
| Chunked Prefill | ✅ | ✅ | 后端配置 |
| Multi-LoRA | ✅ | ✅ | 后端配置 |
| **分布式** |
| Tensor Parallel | ✅ | ✅ | `--tensor-parallel-size` |
| Pipeline Parallel | ✅ | ✅ | `--pipeline-parallel-size` |
| Expert Parallel | ✅ | ✅ | MoE 模型 |
| PD Disaggregation | ⚠️ 实验性 | ✅ 成熟 | 大规模部署 |
| **量化** |
| FP8 | ✅ | ✅ | 后端配置 |
| INT4/INT8 | ✅ | ✅ | 后端配置 |
| AWQ | ✅ | ✅ | 后端配置 |
| GPTQ | ✅ | ✅ | 后端配置 |
| FP4 | ❌ | ✅ | SGLang 独有 |
| **工具调用** |
| Function Calling | ✅ | ✅ | `tools` 参数 |
| Parallel Tool Calls | ✅ | ✅ | `parallel_tool_calls` |
| **嵌入/检索** |
| Embeddings | ✅ | ✅ | `/v1/embeddings` |
| Rerank | ✅ | ✅ | `/rerank` |
| **模型支持** |
| Llama 系列 | ✅ | ✅ | - |
| Qwen 系列 | ✅ | ✅ | - |
| DeepSeek 系列 | ✅ | ⭐ 优化 | SGLang 有特殊优化 |
| Mistral 系列 | ✅ | ✅ | - |
| GLM 系列 | ✅ | ✅ | - |
| Diffusion 模型 | ❌ | ✅ | SGLang Diffusion |

### 4.2 模型-后端推荐矩阵

| 模型 | 推荐 Serving | 原因 |
|------|-------------|------|
| DeepSeek-V3/R1 | SGLang | MLA 优化、大规模 EP 支持 |
| Llama 3.x | 都可以 | 两者支持都很好 |
| Qwen 2.x | 都可以 | 两者支持都很好 |
| Mistral 系列 | vLLM | 略优 |
| GLM 系列 | SGLang | 有特殊支持 |
| Diffusion 模型 | SGLang | 唯一支持 |
| Embedding 模型 | 都可以 | - |

---

## 5. 评估标准与打分体系

### 5.1 评估维度

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Evaluation Framework                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐               │
│   │  Performance │   │  Features    │   │  Stability   │               │
│   │  (40%)       │   │  (30%)       │   │  (20%)       │               │
│   │              │   │              │   │              │               │
│   │ - Throughput │   │ - Coverage   │   │ - Uptime     │               │
│   │ - Latency    │   │ - Native     │   │ - Error Rate │               │
│   │ - Memory     │   │ - Fallback   │   │ - Recovery   │               │
│   └──────────────┘   └──────────────┘   └──────────────┘               │
│                                                                         │
│   ┌──────────────┐   ┌──────────────┐                                  │
│   │  Ecosystem   │   │  Operations  │                                  │
│   │  (5%)        │   │  (5%)        │                                  │
│   │              │   │              │                                  │
│   │ - Community  │   │ - Monitoring │                                  │
│   │ - Docs       │   │ - Debugging  │                                  │
│   │ - Integrations│  │ - Scaling    │                                  │
│   └──────────────┘   └──────────────┘                                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 5.2 详细打分标准

#### 5.2.1 Performance (性能) - 40分

| 指标 | 测试方法 | 评分标准 |
|------|---------|---------|
| **Throughput (吞吐量)** - 15分 | ShareGPT 数据集，测量 tokens/sec | |
| - 单 GPU | 标准测试 | 最高者 15 分，其他按比例 |
| - 多 GPU | TP=2,4,8 测试 | 最高者加分 |
| **Latency (延迟)** - 10分 | P50, P95, P99 延迟 | |
| - Time to First Token | 首 token 延迟 | 最低者 5 分 |
| - Inter-token Latency | token 间隔 | 最低者 5 分 |
| **Memory Efficiency** - 10分 | KV Cache 利用率 | |
| - 内存利用率 | 有效内存占比 | >90% 得 10 分 |
| - 并发容量 | 最大并发请求 | 最高者加分 |
| **Scalability** - 5分 | 多节点扩展效率 | 线性扩展得分高 |

#### 5.2.2 Features (特性) - 30分

| 指标 | 评分标准 |
|------|---------|
| **Native Support (原生支持)** - 15分 | 每个核心特性原生支持得 1-2 分 |
| - 结构化输出 | JSON/Regex/EBNF 支持 |
| - 多模态 | 图像/音频/视频 |
| - 量化 | FP4/FP8/INT4/AWQ/GPTQ |
| - 分布式 | TP/PP/EP/PD |
| **Feature Quality** - 10分 | 特性实现质量 |
| - 性能优化 | 特性性能表现 |
| - API 一致性 | 与 OpenAI 兼容程度 |
| **Extensibility** - 5分 | 扩展新特性的容易程度 |

#### 5.2.3 Stability (稳定性) - 20分

| 指标 | 测试方法 | 评分标准 |
|------|---------|---------|
| **Uptime** - 5分 | 7天连续运行测试 | 99.9% 得满分 |
| **Error Rate** - 5分 | 错误请求占比 | <0.1% 得满分 |
| **Recovery** - 5分 | 故障恢复时间 | <30s 得满分 |
| **Load Test** - 5分 | 高压测试表现 | 无崩溃得满分 |

#### 5.2.4 Ecosystem (生态) - 5分

| 指标 | 评分标准 |
|------|---------|
| **Community Activity** - 2分 | GitHub Stars, Contributors |
| **Documentation** - 2分 | 文档完整度、示例丰富度 |
| **Integrations** - 1分 | 与其他工具的集成 |

#### 5.2.5 Operations (运维) - 5分

| 指标 | 评分标准 |
|------|---------|
| **Monitoring** - 2分 | Prometheus metrics, 日志 |
| **Debugging** - 2分 | 调试工具、错误信息 |
| **Deployment** - 1分 | Docker, K8s 支持 |

### 5.3 评估脚本模板

```python
# ============================================================
# Benchmark Script Template
# ============================================================

import asyncio
import time
from dataclasses import dataclass
from typing import List

@dataclass
class BenchmarkResult:
    throughput_tokens_per_sec: float
    ttft_ms: float  # Time to First Token
    itl_ms: float   # Inter-token Latency
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    memory_utilization: float
    error_rate: float

async def run_benchmark(
    backend_url: str,
    model: str,
    test_prompts: List[str],
    max_tokens: int = 256,
    num_requests: int = 1000,
    concurrency: int = 32
) -> BenchmarkResult:
    """
    运行基准测试
    """
    # 1. Throughput Test
    start_time = time.time()
    total_tokens = 0
    
    # 并发发送请求
    tasks = []
    for prompt in test_prompts[:num_requests]:
        task = send_request(backend_url, model, prompt, max_tokens)
        tasks.append(task)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 计算吞吐量
    successful = [r for r in results if not isinstance(r, Exception)]
    for r in successful:
        total_tokens += r["usage"]["completion_tokens"]
    
    elapsed = time.time() - start_time
    throughput = total_tokens / elapsed
    
    # 2. Latency Analysis
    latencies = [r["latency_ms"] for r in successful]
    ttft_values = [r["ttft_ms"] for r in successful]
    itl_values = [r["itl_ms"] for r in successful]
    
    # 3. Error Rate
    error_rate = len([r for r in results if isinstance(r, Exception)]) / num_requests
    
    return BenchmarkResult(
        throughput_tokens_per_sec=throughput,
        ttft_ms=sum(ttft_values) / len(ttft_values),
        itl_ms=sum(itl_values) / len(itl_values),
        p50_latency_ms=percentile(latencies, 50),
        p95_latency_ms=percentile(latencies, 95),
        p99_latency_ms=percentile(latencies, 99),
        memory_utilization=get_memory_util(backend_url),
        error_rate=error_rate
    )

def calculate_score(result: BenchmarkResult) -> float:
    """计算综合得分"""
    score = 0.0
    
    # Performance Score (40 points)
    # Throughput: 按相对排名给分
    score += min(15, result.throughput_tokens_per_sec / 100)  # 假设 100 tps 为满分
    
    # Latency: 越低越好
    score += max(0, 10 - result.p95_latency_ms / 100)  # 假设 100ms 为基准
    
    # Memory: 越高越好
    score += result.memory_utilization * 10
    
    # Error rate: 越低越好
    score += max(0, 5 - result.error_rate * 50)
    
    return score
```

---

## 6. 多 Serving 协作架构

### 6.1 协作模式

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     Multi-Serving Collaboration Patterns                 │
└─────────────────────────────────────────────────────────────────────────┘

模式 1: 特性路由 (Feature-based Routing)
┌───────────────────────────────────────────────────────────────────────┐
│                                                                       │
│   Client Request                                                      │
│        │                                                              │
│        ▼                                                              │
│   ┌─────────────────────────────────────┐                            │
│   │      Feature Router                 │                            │
│   │  (检测请求需要的特性)                │                            │
│   └─────────────────────────────────────┘                            │
│        │                                                              │
│        ├── 需要 EBNF/Structural Tag ──────────▶ SGLang               │
│        │                                                              │
│        ├── 需要 Diffusion ────────────────────▶ SGLang Diffusion     │
│        │                                                              │
│        ├── 需要 FP4 量化 ─────────────────────▶ SGLang               │
│        │                                                              │
│        ├── DeepSeek 模型 ─────────────────────▶ SGLang (优化)        │
│        │                                                              │
│        └── 其他情况 ──────────────────────────▶ vLLM (默认)          │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘


模式 2: 模型池 (Model Pool)
┌───────────────────────────────────────────────────────────────────────┐
│                                                                       │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │
│   │ vLLM Pool   │  │ SGLang Pool │  │ Specialized │                  │
│   │             │  │             │  │ Pool        │                  │
│   │ - Llama-3   │  │ - DeepSeek  │  │ - Diffusion │                  │
│   │ - Qwen-2    │  │ - GLM       │  │ - Embedding │                  │
│   │ - Mistral   │  │ - Qwen-2    │  │             │                  │
│   └─────────────┘  └─────────────┘  └─────────────┘                  │
│         │                │                │                           │
│         └────────────────┼────────────────┘                           │
│                          ▼                                            │
│                  ┌──────────────┐                                     │
│                  │ Load Balancer│                                     │
│                  └──────────────┘                                     │
│                          │                                            │
│                    Client Request                                     │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘


模式 3: PD 分离 (Prefill-Decode Disaggregation)
┌───────────────────────────────────────────────────────────────────────┐
│                                                                       │
│   ┌─────────────────────────────────────────────────────────────┐    │
│   │                    SGLang Cluster                           │    │
│   │                                                             │    │
│   │   ┌─────────────────┐         ┌─────────────────┐          │    │
│   │   │ Prefill Workers │  KV     │ Decode Workers  │          │    │
│   │   │ (高算力 GPU)     │◀───────▶│ (高显存 GPU)    │          │    │
│   │   │                 │ Transfer │                 │          │    │
│   │   │ - 快速处理 prompt│         │ - 高吞吐生成    │          │    │
│   │   │ - 大批量 prefill │         │ - 长上下文支持  │          │    │
│   │   └─────────────────┘         └─────────────────┘          │    │
│   │                                                             │    │
│   └─────────────────────────────────────────────────────────────┘    │
│                                                                       │
│   优势:                                                               │
│   - 解耦 prefill 和 decode 的资源需求                                 │
│   - 提高整体吞吐量 (SGLang 官方数据: 3-5x 提升)                       │
│   - 适合大规模部署                                                    │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

### 6.2 推荐部署架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Recommended Production Architecture                   │
└─────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────┐
                              │   Users     │
                              └──────┬──────┘
                                     │
                                     ▼
                        ┌────────────────────────┐
                        │     Load Balancer      │
                        │   (Nginx/HAProxy)      │
                        └───────────┬────────────┘
                                    │
                                    ▼
                        ┌────────────────────────┐
                        │     Chat Gateway       │
                        │  (FastAPI/WebSocket)   │
                        │                        │
                        │  - 会话管理             │
                        │  - 请求验证             │
                        │  - 限流/配额            │
                        └───────────┬────────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                        Adapter Layer (核心)                               │
│                                                                           │
│   ┌─────────────────────────────────────────────────────────────────┐    │
│   │                    Model Registry                                │    │
│   │   - 模型 → 后端映射                                              │    │
│   │   - 特性能力矩阵                                                 │    │
│   │   - 健康状态                                                     │    │
│   └─────────────────────────────────────────────────────────────────┘    │
│                                                                           │
│   ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐   │
│   │   vLLM Adapter    │  │   SGLang Adapter  │  │  Future Adapters  │   │
│   │                   │  │                   │  │                   │   │
│   │  - 参数转换       │  │  - 参数转换       │  │  - TRT-LLM        │   │
│   │  - 特性映射       │  │  - 特性映射       │  │  - ONNX Runtime   │   │
│   │  - 错误处理       │  │  - 错误处理       │  │  - ...            │   │
│   └─────────┬─────────┘  └─────────┬─────────┘  └─────────┬─────────┘   │
│             │                      │                      │              │
└─────────────┼──────────────────────┼──────────────────────┼──────────────┘
              │                      │                      │
              ▼                      ▼                      ▼
   ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐
   │   vLLM Cluster     │  │   SGLang Cluster   │  │   Other Serving    │
   │                    │  │                    │  │                    │
   │  ┌──────────────┐  │  │  ┌──────────────┐  │  │                    │
   │  │ vLLM Node 1  │  │  │  │ SGLang Node 1│  │  │                    │
   │  │ (Llama-3-70B)│  │  │  │ (DeepSeek)   │  │  │                    │
   │  └──────────────┘  │  │  └──────────────┘  │  │                    │
   │  ┌──────────────┐  │  │  ┌──────────────┐  │  │                    │
   │  │ vLLM Node 2  │  │  │  │ SGLang Node 2│  │  │                    │
   │  │ (Qwen-2-72B) │  │  │  │ (GLM-4)      │  │  │                    │
   │  └──────────────┘  │  │  └──────────────┘  │  │                    │
   │  ┌──────────────┐  │  │  ┌──────────────┐  │  │                    │
   │  │ vLLM Node 3  │  │  │  │ SGLang Node 3│  │  │                    │
   │  │ (Mistral)    │  │  │  │ (Diffusion)  │  │  │                    │
   │  └──────────────┘  │  │  └──────────────┘  │  │                    │
   └────────────────────┘  └────────────────────┘  └────────────────────┘
```

---

## 7. 实施建议

### 7.1 分阶段实施

```
Phase 1: 单后端验证 (1-2周)
├── 选择一个后端 (推荐 SGLang，特性更全)
├── 实现 Chat Gateway 基础功能
├── 完成 OpenAI API 兼容层
└── 基础性能测试

Phase 2: 双后端集成 (2-3周)
├── 引入第二个后端
├── 实现 Adapter 抽象层
├── 实现特性路由逻辑
└── 模型-后端映射配置

Phase 3: 高级特性 (2-4周)
├── 结构化输出统一接口
├── 多模态支持
├── 监控和可观测性
└── 自动故障转移

Phase 4: 生产优化 (持续)
├── 性能调优
├── 成本优化
├── 安全加固
└── 文档完善
```

### 7.2 关键配置示例

```yaml
# model-serving-config.yaml

backends:
  vllm:
    url: "http://vllm-cluster:8000"
    health_check_interval: 30s
    timeout: 120s
    capabilities:
      - chat_completion
      - streaming
      - json_schema
      - regex
      - multimodal_image
      - multimodal_audio
    
  sglang:
    url: "http://sglang-cluster:8000"
    health_check_interval: 30s
    timeout: 120s
    capabilities:
      - chat_completion
      - streaming
      - json_schema
      - regex
      - ebnf
      - structural_tag
      - multimodal_image
      - multimodal_audio
      - multimodal_video
      - diffusion
      - fp4_quantization

models:
  deepseek-v3:
    preferred_backend: sglang
    reason: "MLA optimization, large-scale EP support"
    
  llama-3-70b:
    preferred_backend: auto
    fallback_order: [vllm, sglang]
    
  qwen-2-72b:
    preferred_backend: auto
    fallback_order: [sglang, vllm]

routing:
  default_backend: vllm
  feature_priority:
    ebnf: sglang
    structural_tag: sglang
    diffusion: sglang
    fp4: sglang
  fallback_enabled: true
  health_check_enabled: true

monitoring:
  metrics_port: 9090
  log_level: INFO
  trace_enabled: true
```

### 7.3 常见问题与解决方案

| 问题 | 解决方案 |
|------|---------|
| 两个后端返回格式不一致 | 在 Adapter 层统一响应格式 |
| 某特性只在单后端支持 | 路由到支持的后端，或提供 fallback |
| 后端故障 | 健康检查 + 自动切换 |
| 性能差异大 | 根据模型特性选择最优后端 |
| 配置复杂 | 使用配置文件 + 动态加载 |

---

## 总结

本架构设计提供了：

1. **统一的适配层**: 通过 Adapter Pattern 屏蔽底层差异
2. **智能路由**: 基于特性需求的自动后端选择
3. **完整的评估体系**: 可量化的后端评估标准
4. **可扩展的架构**: 支持未来接入更多 Serving 后端

关键收益：
- **灵活性**: 用户无需关心底层使用哪个 serving
- **最优性能**: 自动选择最适合的后端
- **高可用**: 多后端互为备份
- **易维护**: 统一接口，降低开发复杂度

---

**文档版本历史**:
- v1.0 (2026-03-14): 初始版本