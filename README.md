# Aurora · AI 面试系统

> 多 Agent 协作的 AI 面试 demo：上传简历 → 智能问答 → 自动评估 → 可视化报告。

![stack](https://img.shields.io/badge/stack-LangGraph%20%2B%20FastAPI%20%2B%20Next.js%20%2B%20ZhipuAI-7c3aed)

## 技术栈

- **Agent 编排**：[LangGraph](https://github.com/langchain-ai/langgraph)（Python）
  - 5 个分工 agent：ResumeParser → QuestionPlanner → Interviewer → FollowUp → Evaluator → Reporter
- **大模型**：智谱 GLM（默认 `glm-4-plus`），通过官方 `zhipuai` SDK
- **后端**：FastAPI + Pydantic
- **前端**：Next.js 14 (App Router) + TypeScript + Tailwind + Framer Motion + Recharts
- **语音**：浏览器原生 `webkitSpeechRecognition`（Chrome / Edge 支持最佳）

## 项目结构

```
interview-new/
├── backend/      FastAPI + LangGraph
└── frontend/     Next.js 14 (深色科技感 UI)
```

## 快速开始

### 1. 后端

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                # 然后填入 ZHIPUAI_API_KEY
uvicorn app.main:app --reload --port 8000
```

访问 `http://localhost:8000/docs` 可看到 Swagger。

环境变量（详见 `.env.example`）：
| 变量 | 必填 | 说明 |
|---|---|---|
| `ZHIPUAI_API_KEY` | ✅ | 智谱 AI API Key，从 [open.bigmodel.cn](https://open.bigmodel.cn) 获取 |
| `ZHIPUAI_MODEL` | ❌ | 默认 `glm-4-plus`，可选 `glm-4-air` / `glm-4-flash` 等 |
| `CORS_ORIGINS` | ❌ | 前端来源，多个用逗号分隔 |
| `SELECTOR_STRATEGY` | ❌ | 选题策略：`round_robin` / `thompson` / `linucb`（默认） / `ia_linucb`（论文 §3.6 提出的信息增强 LinUCB，Fisher 项默认 `γ₀=0.9`） |
| `DIFFICULTY_STRATEGY` | ❌ | 难度控制：`heuristic` / `pi_control`（默认） |
| `LLM_MULTI_JUDGE_COUNT` | ❌ | 多评委数量 J，默认 `1`；论文实验默认 `5` |
| `JUDGE_AGGREGATOR` | ❌ | 评委聚合策略：`trimmed`（默认，对称剪枝均值）或 `rwmj`（论文 §3.8 提出的在线可靠性加权聚合） |
| `JUDGE_OUTLIER_TRIM` | ❌ | trimmed 模式下的剪枝比例，默认 `0.0` |

### 2. 前端

```bash
cd frontend
pnpm install       # 或 npm install / yarn
pnpm dev
```

打开 `http://localhost:3000` 即可。

前端通过 `next.config.mjs` 的 `rewrites` 把 `/api/*` 代理到 `http://localhost:8000`，无需手动配置 CORS。

如需指向其它后端，启动前设置：

```bash
BACKEND_URL=https://your-backend.example.com pnpm dev
```

## 使用流程

1. 首页 → 点击「开始面试」
2. `/upload` 拖拽简历（PDF/DOCX/TXT），选择目标职位与难度 → 点击「开始面试」
3. `/interview/[id]` AI 会主持 8 道结构化问题，最多每题追问 1 次
   - 可以用键盘输入，或点击麦克风按钮录制语音
   - `⌘ / Ctrl + Enter` 发送
4. 答完所有题目自动跳转 `/report/[id]`，查看综合评分、雷达图、优势 / 待提升 / 建议 / 逐题评审
5. 右上角「打印 / 导出 PDF」可生成 PDF 报告

## Agent 流水线

```
ResumeParserAgent  → 抽取简历结构化画像
QuestionPlannerAgent → 5 维度共 8 题
InterviewerAgent     → 主持问答（HITL）
FollowUpAgent        → 智能追问 (≤ 1 次/题)
EvaluatorAgent       → 逐题评分
ReporterAgent        → 汇总维度分 + 推荐结论
```

## 已知简化（demo 取舍）

- 无用户系统、会话存储在进程内（重启即清空）
- 评估为单次 LLM 调用，未做多轮自洽校验
- PDF 导出走浏览器打印样式，未集成 Puppeteer
- 浏览器原生 STT 主要在 Chrome / Edge 中可用

## License

MIT
