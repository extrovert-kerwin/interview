# 评估报告 · 算法与改动总结

本文档记录 Aurora 面试系统的 **评估算法栈** 与本轮迭代在前端可视化上的改动。算法细节均给出 `文件:行号` 引用，方便定位源码。

> Backend evaluation pipeline 早已存在，本轮主要工作是补全报告页对这些算法输出的呈现（知识图谱、热力图、待生成状态、富信息侧栏等）。

---

## 0 · 评估全流程

```
简历解析 ──┐
          ▼
       问题计划 (question_planner) ──► 候选回答 (interviewer + ASR + video sampler)
                                                 │
                                                 ▼
                                       evaluator.evaluate()
                                  ┌────────────┴───────────────┐
                                  ▼                            ▼
                          多评审 LLM 评分                 本地启发式兜底
                          (Prometheus/G-Eval)            (_score_item)
                                  │
                                  ▼
                          Validator + 一致性聚合
                          (trimmed mean / RWMJ)
                                  │
                                  ▼
                          可靠度加权 + Calibrator
                          (linear / Platt)
                                  │
                          ┌───────┴────────┐
                          ▼                ▼
                  evaluations[]    fold_into_memory
                          │        (bandit + memory)
                          ▼
                    reporter.build_report()
                ┌──────────┼────────────────┐
                ▼          ▼                ▼
          总分公式     知识点覆盖      沟通/视频维度
                │          │                │
                └──────────┴────────┬───────┘
                                    ▼
                            FinalReport JSON
                                    │
                                    ▼
                        前端报告页 (新加: 知识图谱 + 热力图 + 待生成态)
```

---

## 1 · 单题评分（rubric scoring）

**位置:** `backend/app/agents/evaluator.py`

### 1.1 7 维 rubric 与权重（`evaluator.py:63-71`）

| Key | 维度 | 权重 |
| --- | --- | ---: |
| relevance | 相关性 | 0.18 |
| knowledge | 知识覆盖 | 0.20 |
| specificity | 证据具体性 | 0.18 |
| reasoning | 逻辑推理 | 0.16 |
| completeness | 结构完整 | 0.14 |
| reflection | 复盘改进 | 0.08 |
| follow_up | 追问响应 | 0.06 |

每维度按 Prometheus 风格的 0/50/70/90 段位描述定义（`evaluator.py:96-136`）。

### 1.2 预分类（`evaluator.py:172-186`）

- `[跳过`、长度 < 8、或带"我不会"等 marker 且 < 80 字 → 直接 score=0 并标 `off_topic`。
- 其余 → "可评分"桶，进入 LLM 批量打分。

### 1.3 多评审聚合（`evaluator.py:368-552`）

- 默认 trimmed mean（每维度对称截尾），裁剪比例 `judge_outlier_trim ∈ [0, 0.4]`。
- RWMJ 模式：在线 EMA 维护每个 judge 的偏差和方差，按可信度加权。
- 一致性指标 `agreement = max(0, 1 − mean_spread/100)`，传给 calibrator 做置信门控。
- Validator (`validator.py:41-89`) 强制 7 维齐全、值在 [0,100]、max-spread ≤ 45；不满足则整 ensemble fail。

### 1.4 可靠度（`_reliability`，`evaluator.py:916-922`）

```
length_factor = min(1, len(answer)/180)
variance      = var(sub_scores)
consistency   = max(0.62, 1 − variance/1400)
speech_factor = 0.04 if 有 speech metrics else 0
reliability   = clamp(0.42 + 0.35·length_factor + 0.19·consistency + speech_factor,
                     0.35, 0.98)
```

### 1.5 单题校准（`_calibrate`，`evaluator.py:925-931`）

```
base   = Σ sub[k] · weight[k]
score  = base · (0.82 + 0.18·reliability)
score -= 8  if len(answer) < 45
score -= 3  if speech.confidence < 0.55
return clamp(score, 0, 96)
```

之后若启用全局 calibrator（§6），再叠加一次 linear/Platt 的非线性映射。

### 1.6 启发式兜底（`_score_item`，`evaluator.py:774-833`）

LLM 整条链路失败时使用同一 rubric 权重，子分由文本特征计算：term 重合率、数字/结果 marker 数、推理标记、follow-up 长度等。保证报告永远能产出。

### 1.7 单题输出字段（`evaluator.py:664-682`）

`id, category, knowledge_points, score (0-96), rubric_scores{label,score,weight}, evidence_quality, uncertainty, covered_knowledge_points, strengths, gaps, judge_panel, evaluation_notes`。

---

## 2 · 知识点覆盖度

**位置:** `_knowledge_coverage`，`backend/app/agents/reporter.py:319-394`

对每个预设知识点维护四元组 `(planned, answered, covered, score_total)`。

### 2.1 单点公式（`reporter.py:359-377`）

```
avg_score     = round(score_total / answered_count) if answered else 0
answer_rate   = answered_count / planned_count
explicit_rate = covered_count  / planned_count
coverage_rate = round(max(answer_rate·0.55, explicit_rate), 2)
coverage_score = clamp(round(explicit_rate·45 + answer_rate·25 + avg_score·0.30), 0, 100)
```

`coverage_score` 是知识图谱节点颜色的依据。

### 2.2 等级阈值（`_knowledge_level`，`reporter.py:576-585`）

| coverage_score | level |
| ---: | --- |
| ≥ 85 | 覆盖充分 |
| ≥ 70 | 覆盖较好 |
| ≥ 50 | 部分覆盖 |
| > 0 | 覆盖不足 |
| 0 | 未覆盖 |

### 2.3 整体汇总（`reporter.py:379-394`）

```
overall_rate  = total_answered / total_planned
overall_score = round(mean(item.coverage_score))
strongest = top-4 by (coverage_score, answered_count)
weakest   = bot-4 by (coverage_score, answered_count)
```

---

## 3 · 维度聚合（5 个能力方向）

**位置:** `_dimension_scores`，`reporter.py:192-208`；权重 `reporter.py:45-51`

```
DIMENSIONS       = ["技术深度","项目经验","系统设计","沟通表达","学习能力"]
DIMENSION_WEIGHT = { 1.18,   1.08,    1.12,    0.92,    0.88 }

reliability = max(0.35, evidence_quality/100)
dim_score   = Σ(score · reliability) / Σ(reliability)        # 同一 dim 桶内
```

`_normalize_category` 把 LLM 给出的自由文本类别 fuzzy 映射到 5 维之一。`_dimension_details` 额外补 `level / evidence_count / skipped_count / insight`。

---

## 4 · 总分公式

**位置:** `_overall_score`，`reporter.py:165-189`

```
base = Σ(score · reliability · DIMENSION_WEIGHT[dim])
       / Σ(reliability · DIMENSION_WEIGHT[dim])

coverage_adj      = (knowledge.overall_score − 65) · 0.10
completion_adj    = completion.completion_rate · 6 − 4
communication_adj = clamp(audio+video 调节, ±5)        # §6
uncertainty_adj   = − min(7, mean(uncertainty) / 14)
skip_penalty      = min(skipped · 3.5, 16)

overall = clip( base + coverage_adj + completion_adj
              + communication_adj + uncertainty_adj
              − skip_penalty, 0, 100 )
```

无任何回答时 `overall = 0`（提前 return）。

---

## 5 · 推荐 & 风险标记

### 5.1 Recommendation（`_recommend`，`reporter.py:614-623`）

| 条件 | 标签 |
| --- | --- |
| `answered == 0` | 不推荐 |
| `≥ 85` | 强烈推荐 |
| `≥ 70` | 推荐 |
| `≥ 55` | 待定 |
| else | 不推荐 |

### 5.2 Risk flags（`_risk_flags`，`reporter.py:512-531`，最多 8 条）

| level | trigger |
| --- | --- |
| high | `skipped ≥ 2` → 跳题偏多 |
| high | `overall < 55` → 综合得分偏低 |
| medium | `knowledge.overall_score < 55` → 知识点覆盖不足 |
| medium | 任意 `dimension.score < 50` → `{dim} 证据不足` |
| medium | `audio.nervousness ≥ 70` 或 `video.visual_nervousness ≥ 70` |
| low | 无语音 / 无视频样本 |

---

## 6 · 沟通分析（音视频）

**位置:** `reporter.py:252-316, 671-788`

### 6.1 流畅度（`_fluency_score`，`:671-683`）

```
score = 72
+= round((mean(conf) − 0.7) · 30)
−= round(max(0, silence_rate − 0.28) · 70)
+= round((stability − 0.55) · 18)
−= 8 if wpm < 90 or wpm > 260
```

### 6.2 音频紧张度（`_audio_nervousness`，`:686-698`）

```
score = 20
+= max(0, silence_rate − 0.2) · 90
+= max(0, 0.58 − stability) · 55
+= 14 if avg_volume < 0.025
+= 12 if wpm < 80 or wpm > 280
```

### 6.3 视频紧张度（`_video_nervousness`，`:701-711`）

```
score = 18
+= min(45, motion · 1.8)
+= max(0, 0.86 − presence_rate) · 38
+= max(0, 0.75 − center_rate) · 28
```

### 6.4 出镜/构图/打光（`reporter.py:761-788`）

```
presence_score = presence_rate · 100
framing_score  = center_rate   · 100
lighting_score = 90 if 65≤brightness≤185 else 72 if 45≤brightness≤210 else 45
motion_quality = 稳定 (<8) / 轻微波动 (<22) / 波动偏大
```

### 6.5 反向打通到总分（`_communication_adjustment`，`:658-668`）

```
adj = (fluency           − 65) · 0.04
    + (45 − nervousness)       · 0.025
    + (avg_attention     − 65) · 0.03
    + (45 − visual_nervousness) · 0.02
return clamp(adj, −5, +5)
```

这是音视频信号唯一直接影响 `overall_score` 的入口。

---

## 7 · 在线校准（calibrator）

**位置:** `backend/app/services/calibration.py`

支持 `linear` 和 `platt` 两种模式，应用时（`:39-51`）：

```
x = clamp(raw_unit, 0, 1)
y = sigmoid(a·(x−0.5) + b)            # platt
y = slope·x + intercept               # linear
y = clamp(y, 0, 1)

# consensus gate：多评审一致 → 信校准；分歧大 → 拉回原分
blend = 0.55 + (1−0.55) · clamp(consensus, 0, 1)
y     = blend·y + (1−blend)·x
```

`fit_platt`（`:105-146`）需要 ≥ 5 对人工标注 (raw, human)，用 lr=0.3 跑 500 步梯度，并附带闭式 linear 基线和 Pearson r² 作为 `confidence`。结果持久化到 `backend/data/calibration.json`。

`evidence_quality / uncertainty` 不来源于 calibrator，而是 §1.4 的 `reliability·100` 及其互补。前者表征"单题证据有多扎实"，calibrator 的 `confidence` 表征"评分器整体可信度"，二者是分离的。

---

## 8 · 题目自适应：Bandit 与难度

**说明：** 这两个组件 **不直接修改分数**，但通过决定下一题的方向 / 难度，间接影响 `evaluations[]` 的分布。

### 8.1 Bandit（`backend/app/services/bandit.py`）

- 默认 `round_robin`，序列固定（`:294`）。
- 可选 `linucb` / `thompson` / `ia_linucb`。
- 上下文 `CTX_DIM=6 = [bias, ability, 1−cov_ratio, topic_mean, max(gap,resume), 1−recency]`（`:156-182`）
- Reward：`diff_match + λ_cov·cov_bonus + λ_gap·gap_bonus + λ_resume·resume_aff`（`:185-202`）
- 在 `len(ARMS)` 轮后强制覆盖未触达类别（`:325-333`）

### 8.2 难度（`backend/app/services/difficulty.py`）

- Heuristic（`:28-38`）：3 题滑窗均分 > 0.78 → +0.10；< 0.42 → −0.10。
- PI 控制（`:41-62`）：`raw = ability + Kp·instant + Ki·avg_err`，再 `0.85·raw + 0.15·base` 锚定，clamp [0.05, 0.95]。

---

## 9 · 关键常量速查

| 常量 | 值 | 位置 |
| --- | --- | --- |
| 单题分上限 | 96 | `evaluator.py:931` |
| 短答惩罚 | −8 (< 45 字) | `evaluator.py:927` |
| ASR 低置信惩罚 | −3 (< 0.55) | `evaluator.py:929` |
| 可靠度公式系数 | 0.42 / 0.35 / 0.19 / 0.04 | `evaluator.py:916-922` |
| 多评审最大 spread | 45 | `validator.py:71` |
| 维度权重 | 1.18 / 1.08 / 1.12 / 0.92 / 0.88 | `reporter.py:45-51` |
| 覆盖度权重 | 0.45·explicit + 0.25·answer_rate + 0.30·avg_score | `reporter.py:367` |
| 覆盖率公式 | `max(answer·0.55, explicit)` | `reporter.py:366` |
| 推荐阈值 | 85 / 70 / 55 | `reporter.py:614-623` |
| 跳题惩罚 | `min(skipped·3.5, 16)` | `reporter.py:185` |
| 不确定性扣分 | `−min(7, mean_unc/14)` | `reporter.py:188` |
| 沟通调节上下限 | ±5 | `reporter.py:668` |
| 计算师一致门控起点 | `consensus_floor = 0.55` | `calibration.py:36` |
| Platt 最少样本 | 5 | `calibration.py:110` |
| Platt lr / iters | 0.3 / 500 | `calibration.py:114-115` |
| Bandit eta-hint bonus | +0.25 | `bandit.py:312` |
| 难度阈值（heuristic） | 0.78 / 0.42，± 0.10 | `difficulty.py:34-38` |

---

## 10 · 本轮前端改动（围绕评估输出的可视化）

| 模块 | 路径 | 用到的算法输出 |
| --- | --- | --- |
| **报告页 pending/missing 三态** | `app/report/[id]/page.tsx` | 区分 finalize 未跑完 vs. 真 404；pending 态可手动触发 `/finalize` 并每 5s 自动重试。 |
| **知识图谱（KnowledgeGraph）** | `components/KnowledgeGraph.tsx` | `knowledge_coverage.items[]` + `per_question[].knowledge_points`。节点大小 = `planned + answered`，颜色按 `coverage_score` 落入 `≥80 / ≥60 / ≥40 / <40` 四档（emerald / cyan / amber / rose）。 |
| **逐题热力图（QuestionRubricGrid）** | `components/QuestionRubricGrid.tsx` | `per_question[].rubric_scores`（7 维 × N 题）。色阶 ≥80 / ≥65 / ≥50 / ≥30 / <30，行尾给均分，列尾给总分。 |

### 10.1 知识图谱布局算法

采用 `d3-force` 实现力导布局（`components/KnowledgeGraph.tsx`）：

```
forces = {
  link:    distance = 150 (root-cat) / 95 (cat-kp)
           strength = 0.85 / 0.45
  charge:  -220
  collide: r + 14, 强度 0.95, iterations=2
  center:  weak (0.04)
  radial:  category → 160, kp → 250, root 不受力
  x/y cluster: kp 朝各自 category 的方位再加一个 (0.18) 弱拉力
}
```

- 初始位置用同心圆估算给定，alpha 衰减 0.035 让模拟很快收敛。
- 节点支持 pointer 拖拽：`fx/fy` 在拖拽中钉住，松开仍保留位置；右下「松开 X」按钮释放回浮动。
- 「重新布局」按钮清空所有 `fx/fy`、重启 `alpha=1` 的模拟。
- 边界 clamp：每个 tick 强制 `n.x ∈ [r+24, W-r-24]`、`n.y` 同理，节点不会跑出画布。

### 10.2 富信息侧栏

无 hover 时：展示「掌握得最好 / 还需要补的」各 top-3（直接复用 `coverage.strongest/weakest` 的逻辑）。
hover category：展示方向均分。
hover knowledge point：展示掌握/均分/覆盖三宫格 + 覆盖率进度条 + 「出现在」哪几道题（按 `kpToQuestions` 反向索引，列出 qid / category / 该题分数）。

---

## 11 · 参考文件

- 评估器：`backend/app/agents/evaluator.py`（1011 行）
- 报告合成：`backend/app/agents/reporter.py`（812 行）
- 校准：`backend/app/services/calibration.py`
- Bandit：`backend/app/services/bandit.py`
- 难度自适应：`backend/app/services/difficulty.py`
- 多评审校验：`backend/app/services/validator.py`
- 前端报告页：`frontend/app/report/[id]/page.tsx`
- 知识图谱：`frontend/components/KnowledgeGraph.tsx`
- 热力图：`frontend/components/QuestionRubricGrid.tsx`
- 数据类型：`frontend/lib/api.ts` (`FinalReport`)
