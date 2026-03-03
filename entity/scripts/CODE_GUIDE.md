# 意图匹配分析平台 — 代码说明

> 本文档供 AI 快速定位修改点，无需全量阅读项目上下文。
> 平台定位：意图匹配结果分析 + 权重词表自动化迭代平台

## 项目入口

- **后端**: `scripts/web_app.py` — Flask 服务端（端口 5000）
- **前端**: `scripts/templates/index.html` — 单文件 SPA

## 目录结构（关键文件）

```
entity/
├── scripts/
│   ├── web_app.py                    # Flask 后端（主入口）
│   ├── templates/index.html          # 前端页面（单文件，含 CSS + JS）
│   ├── CODE_GUIDE.md                 # 本文档
│   ├── modules/
│   │   ├── query_segmenter.py        # AC自动机分词器
│   │   ├── weight_calculator.py      # 权重计算器
│   │   ├── feature_extractor.py      # 特征词自动提取器（NEW）
│   │   └── weight_scorer.py          # AI权重打分器（NEW）
│   └── common/
│       ├── file_manager.py           # 文件管理器
│       ├── config.py                 # 配置管理器
│       └── llm_api.py               # 大模型 API 调用
├── prompts/
│   ├── query_rewrite_3d_prompt.md    # 三维度转写提示词
│   ├── intent_select_prompt.md       # AI意图筛选提示词
│   ├── feature_extract_prompt.md     # 特征词提取提示词（NEW）
│   └── weight_score_prompt.md        # 权重打分提示词（NEW）
├── result/global/weighted/           # 全局权重词表（不再按领域区分）
│   └── weighted_words.json           # 权重词表文件
├── uploads/                          # 上传文件暂存目录
└── config/                           # 配置文件
```

## 核心计算公式

| 编号 | 公式 | 说明 |
|------|------|------|
| F1 | `单词得分 = 层级权重 × 词权重(意图级)` | 层级：核心词=1.0, 发散词=0.8, 同义词=0.6 |
| F2 | `原始得分(I) = Σ 单词得分(word_j, I)` | 对命中的所有词求和 |
| F3 | `归一化得分(I) = 原始得分(I) / 最大可能得分(I)` | 跨意图可比 |
| F4 | `IDF(word) = 1/log₂(关联意图数+1)` | 共享词自动降权 |
| F5 | `最终得分(I) = max(四路得分)` | 四路并行取最高 |
| F6 | `增强得分(I) = 基础得分 × (1 + 0.1×(命中维度数-1))` | 多源命中加分 |
| F7 | `反向权重 = (标杆应得分 - 已知贡献) / 层级权重` | 反向校验 |
| F8 | `覆盖度 = |标杆特征词∩命中词| / |标杆全部特征词|` | 诊断用 |
| F9 | `候选集 = {I | 归一化得分 ≥ 0.4}，取前10` | 阈值+TopK |

## 特征词层级体系

> 新层级名称，兼容旧 L1_事项词 / L2_动作词 / L3_场景词

| 新层级名 | 层级权重 | 旧名称（兼容） | 说明 |
|---------|---------|---------------|------|
| `核心词` | 1.0 | L1_事项词 | 从意图名/原文直接提取的专业术语 |
| `发散词` | 0.8 | L2_动作词 | 核心词的俗称、口语化表述、常见搭配 |
| `同义词` | 0.6 | L3_场景词 | 发散词的同义表达，同义词权重一致 |

层级读取兼容逻辑：`layer_key` 取层级字符串前两个字符匹配配置（`核心`/`发散`/`同义`），若为旧格式 `L1`/`L2`/`L3` 也兼容。

## 权重词表结构

### 新格式（一意图一词一分）

```json
{
  "意图映射表": {
    "失业保险金申领": {
      "核心词": ["失业保险金", "失业金"],
      "发散词": ["申领", "申请", "领取"],
      "同义词": ["审核", "资格"]
    }
  },
  "词权重表": {
    "失业保险金": {
      "失业保险金申领": { "权重": 0.98, "理由": "核心专业术语" },
      "了解失业保险金": { "权重": 0.80, "理由": "了解类区分度低" }
    }
  }
}
```

### 旧格式（兼容读取）

```json
{
  "意图映射表": {
    "失业保险金申领": {
      "L1_事项词": ["失业保险金"],
      "L2_动作词": ["申领"]
    }
  },
  "词权重表": {
    "失业保险金": { "权重": 0.98, "理由": "核心专业术语" }
  }
}
```

兼容逻辑：读取 `词权重表[word]` 时，若含 `"权重"` 键则为旧格式（对所有关联意图使用同一权重），否则为新格式。

## 后端关键函数（web_app.py）

### 核心逻辑函数

| 函数 | 作用 |
|------|------|
| `load_rewrite_prompt()` | 加载三维度转写提示词 |
| `load_intent_select_prompt()` | 加载意图筛选提示词 |
| `match_4d()` | **四路并行匹配**：原始问 + 三维度转写，返回 `(top_intents, all_hit_words, results_all)` |
| `format_intent_features()` | 格式化命中特征词文本 |
| `format_rewrite_display()` | 格式化转写结果展示 |
| `ai_select_intent()` | AI大模型筛选最终意图 |
| `diagnose_mismatch()` | 诊断匹配不一致原因，返回**结构化 dict** |
| `run_intent_match_task()` | 后台任务主函数 |

### API 路由

| 路由 | 方法 | 作用 |
|------|------|------|
| `/` | GET | 返回前端页面 |
| `/api/domains` | GET | 获取可用领域列表及权重词表 |
| `/api/start` | POST | 上传Excel并启动分析任务 |
| `/api/progress/<task_id>` | GET(SSE) | 实时推送任务进度 |
| `/api/download/<task_id>` | GET | 下载结果Excel |
| `/api/upload-weights` | POST | 上传权重词表文件（multipart） |
| `/api/upload-weights-json` | POST | 上传权重词表（JSON body） |
| `/api/history` | GET | 列出历史分析结果 |
| `/api/history-detail` | GET | 读取指定历史结果JSON |
| `/api/intent-weights` | POST | 获取指定意图的全量特征词及权重分 |
| `/api/feature-extract` | POST | 启动AI特征词提取（NEW） |
| `/api/feature-extract/progress/<task_id>` | GET(SSE) | 特征词提取进度（NEW） |
| `/api/feature-extract/merge` | POST | 预览+确认合并到权重词表（NEW） |
| `/api/weight-score` | POST | 对特征词执行AI打分（NEW） |
| `/api/weight-score/validate` | POST | 执行反向校验（NEW） |

### 数据流

```
用户上传 Excel → 读取原始问 → 三维度AI转写
→ 四路并行AC匹配（原始问 + 三维度各自独立）
→ 权重计算（含归一化 + IDF衰减 + 多源加分）
→ 阈值过滤(top_intents, 前10) + 全量得分
→ AI筛选最终意图（多候选 或 低置信度时触发）
→ 诊断分析（结构化，含覆盖度/竞争意图/修复建议）
→ 构建 record/detail → SSE推送前端
```

### 分析结果 → 词表迭代联动

```
分析功能输出 Excel → 用户下载审阅 → 上传到特征词管理功能
→ 仅处理标杆≠算法的行中：
  - "权重分表意图不全" → 为标杆意图生成特征词
  - "特征词未命中" → 补充发散词/同义词
  - 其他类别（大模型筛选/topK不全）→ 仅展示，不处理
```

### 结果记录结构（record）

```python
record = {
    '序号': int,
    '原始问题': str,          # 截断80字
    '转写结果': str,          # [情形] xxx | [群众语言] xxx | [官方表达] xxx
    '转写来源': str,          # 'AI三维度' 或 '原始'
    '算法意图': str,          # 最终选中的意图
    '全量意图': str,          # 逗号分隔的所有候选意图名
    '意图特征词': str,        # 格式：意图名(得分)(命中词1、词2)
    '全量特征词定位': str,    # 全量命中记录（仅查看）
    '分析结果': dict/str,     # 结构化诊断（dict）或旧文本（str，兼容）
    '标杆意图': str,          # 来自 Excel 中的标杆列
    '是否一致': str,          # '✓' 或 '✗'
    '详情': dict              # 详细数据
}
```

### 诊断结果结构（新格式）

```python
diagnosis = {
    '诊断类别': str,         # 枚举：大模型筛选问题/权重分表意图不全/topK取得不全/特征词未命中/特征词匹配不足
    '诊断详情': str,         # 详细文本
    '转写覆盖度': float,     # 公式 F8
    '竞争意图': str,         # Top-1 竞争意图名
    '竞争得分差': float,     # Top-1 得分 - 标杆得分
    '修复建议': list          # ["补充特征词: xxx", "调整权重: yyy"]
}
```

### 详情结构（detail）

```python
detail = {
    '原始问题_完整': str,
    '转写结果': str,
    '全量意图得分': [{'意图': str, '得分': float, '命中词数': int}],
    '全量意图得分_无阈值': [{'意图': str, '得分': float, '命中词数': int}],
    '全量命中词': {'意图名': ['词1', '词2']},
    '诊断分析': dict/str     # 新格式dict或旧格式str
}
```

## 模块说明

### feature_extractor.py（NEW）

特征词自动提取器，支持两种模式：

| 方法 | 作用 |
|------|------|
| `extract_from_intents(intents)` | 模式A：从意图清单AI生成三维度特征词 |
| `extract_from_match_results(results)` | 模式B：从匹配结果提取特征词（仅处理权重缺失/特征词未命中） |
| `merge_into_weights(new, path)` | 增量合并到权重词表，支持冷启动（文件不存在自动创建），输出变更日志 |

### weight_scorer.py（NEW）

AI权重打分器：

| 方法 | 作用 |
|------|------|
| `score_features(intent_map, all_intents)` | 分批AI打分（10~15词/批） |
| `apply_idf_decay(weights, intent_map)` | IDF衰减 |
| `reverse_validate(weights, benchmarks)` | 反向校验 |
| `generate_changelog(old, new)` | 变更日志 |

### AI 打分规则卡

| 维度 | 分值影响 |
|------|---------|
| 专业度 | 强专业0.90~1.00 / 半专业0.75~0.89 / 通用0.60~0.74 |
| 排他性 | 2~3意图扣0.05 / 4+扣0.10 |
| 上下文独立性 | 独立可判+0.05 |
| 反向校验 | 与F7推导值±0.10 |

`有效权重 = (专业度 - 排他性扣分 + 上下文加分) × IDF(word)`

## 前端关键函数（index.html）

| 函数 | 作用 |
|------|------|
| `init()` | 页面初始化 |
| `loadDomains()` | 加载领域+权重词表 |
| `switchWeightsMode(mode)` | 切换权重词表模式 |
| `listenProgress(taskId)` | SSE 监听任务进度 |
| `appendResultRow(r)` | 向结果表格追加一行 |
| `showDetail(idx)` | 打开详情弹窗 |
| `toggleIntentFeatures(...)` | 展开意图特征词 |
| `loadHistory()` | 加载历史分析结果 |
| `switchTab(tab)` | 切换"分析"/"特征词管理"Tab（NEW） |
| `startFeatureExtract()` | 启动特征词提取（NEW） |
| `previewMerge()` | 预览合并结果（NEW） |
| `confirmMerge()` | 确认合并到词表（NEW） |

## 配置默认值（config.py）

| 配置 | 值 |
|------|-----|
| 层级权重 | `{"L1": 1.0, "L2": 0.8, "L3": 0.6}` |
| 阈值 min_score | 0.4 |
| TopK | 10 |

> 层级键：支持 `L1`/`L2`/`L3` 和 `核心`/`发散`/`同义` 两种前缀匹配。

## 修改指南

### 修改结果表格列

- **后端**: `run_intent_match_task()` 中的 `record` 字典
- **前端**: `appendResultRow()` + `<thead>` 表头

### 修改详情弹窗

- **后端**: `run_intent_match_task()` 中的 `detail` 字典
- **前端**: `showDetail()`

### 修改匹配逻辑

- `match_4d()` → 四路并行核心
- `WeightCalculator.calculate()` → 权重计算（含归一化+IDF）
- `QuerySegmenter.segment()` → AC自动机分词

### 修改诊断分析

- `diagnose_mismatch()` → 结构化诊断（5种类别）

### 修改特征词提取/打分

- `FeatureExtractor` → 提取逻辑
- `WeightScorer` → 打分+校验

### 修改阈值/配置

- `config/` + `config.py` DEFAULT_* 值

### 新增 API

- 在 `# ===== Flask 路由 =====` 部分添加
- 参考 `/api/intent-weights` 实现模式

## 系统能力边界

| 能处理 | 不能处理 |
|--------|---------|
| 关键词明确型 ✅ | 隐含意图（完全无关键词）❌ |
| 口语化/别称型 ✅ | 否定/反义语义 ❌ |
| 场景推理型 ⚠️ 部分 | 多意图混合 ⚠️ |

补偿机制：AI转写补隐含词、第4路原始问直接匹配、负面清单、低置信度触发AI筛选。
