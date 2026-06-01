"use client";

import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceRadial,
  forceSimulation,
  forceX,
  forceY,
  Simulation,
  SimulationLinkDatum,
  SimulationNodeDatum,
} from "d3-force";
import { motion } from "framer-motion";
import { Hand, Move, Network, RotateCw, Sparkles, Target } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { FinalReport } from "@/lib/api";

type Coverage = NonNullable<FinalReport["knowledge_coverage"]>;
type KCItem = Coverage["items"][number] & {
  questions?: { id: string; category: string; answered?: boolean; covered?: boolean; score?: number }[];
};
type PerQ = FinalReport["per_question"][number];

interface Props {
  coverage: Coverage;
  perQuestion: PerQ[];
  position: string;
}

interface SimNode extends SimulationNodeDatum {
  id: string;
  label: string;
  kind: "root" | "category" | "kp";
  r: number;
  score?: number;
  level?: string;
  planned?: number;
  answered?: number;
  avg?: number;
  category?: string;
  questionIds?: string[];
}

interface SimEdge extends SimulationLinkDatum<SimNode> {
  source: string | SimNode;
  target: string | SimNode;
  strength: number;
  kind: "root-cat" | "cat-kp";
}

const PALETTE = {
  excellent: "#34d399",
  good: "#22d3ee",
  fair: "#fbbf24",
  poor: "#fb7185",
  neutral: "#a78bfa",
};

function scoreTint(score?: number) {
  if (score == null) return PALETTE.neutral;
  if (score >= 80) return PALETTE.excellent;
  if (score >= 60) return PALETTE.good;
  if (score >= 40) return PALETTE.fair;
  return PALETTE.poor;
}

function scoreLabel(score?: number) {
  if (score == null) return "未评估";
  if (score >= 80) return "掌握";
  if (score >= 60) return "熟悉";
  if (score >= 40) return "薄弱";
  return "缺口";
}

const W = 760;
const H = 600;
const CX = W / 2;
const CY = H / 2;

function radiusForKp(item: KCItem) {
  const weight = (item.planned_count || 0) + (item.answered_count || 0);
  return Math.max(15, Math.min(32, 13 + weight * 4));
}

function buildGraph(coverage: Coverage, perQuestion: PerQ[], position: string) {
  const items = (coverage.items || []) as KCItem[];

  const kpToQuestions = new Map<string, { qid: string; category: string; score: number }[]>();
  const kpCategoryVotes = new Map<string, Map<string, number>>();
  perQuestion.forEach((q, idx) => {
    const qid = q.id || `Q${idx + 1}`;
    (q.knowledge_points || []).forEach((kp) => {
      if (!kpToQuestions.has(kp)) kpToQuestions.set(kp, []);
      kpToQuestions.get(kp)!.push({ qid, category: q.category, score: q.score });
      if (!kpCategoryVotes.has(kp)) kpCategoryVotes.set(kp, new Map());
      const m = kpCategoryVotes.get(kp)!;
      m.set(q.category, (m.get(q.category) || 0) + 1);
    });
  });

  const pickCategory = (item: KCItem): string => {
    const votes = kpCategoryVotes.get(item.name);
    if (votes && votes.size > 0) {
      let best = "";
      let bestN = -1;
      votes.forEach((n, c) => {
        if (n > bestN) {
          bestN = n;
          best = c;
        }
      });
      if (best) return best;
    }
    return item.questions?.[0]?.category || "通用";
  };

  const byCategory = new Map<string, KCItem[]>();
  items.forEach((item) => {
    const cat = pickCategory(item);
    if (!byCategory.has(cat)) byCategory.set(cat, []);
    byCategory.get(cat)!.push(item);
  });
  const categories = Array.from(byCategory.entries()).sort((a, b) => b[1].length - a[1].length);

  const nodes: SimNode[] = [];
  const edges: SimEdge[] = [];
  const catAngle = new Map<string, number>();

  nodes.push({
    id: "__root",
    label: position || "目标岗位",
    kind: "root",
    r: 40,
    x: CX,
    y: CY,
    fx: CX,
    fy: CY,
  });

  categories.forEach(([cat, kps], ci) => {
    const angle = (ci / categories.length) * Math.PI * 2 - Math.PI / 2;
    catAngle.set(cat, angle);
    const cxCat = CX + 160 * Math.cos(angle);
    const cyCat = CY + 160 * Math.sin(angle);
    const catId = `cat:${cat}`;
    const catAvg = kps.reduce((s, k) => s + k.coverage_score, 0) / Math.max(kps.length, 1);
    nodes.push({
      id: catId,
      label: cat,
      kind: "category",
      r: 26,
      x: cxCat,
      y: cyCat,
      score: Math.round(catAvg),
      category: cat,
    });
    edges.push({ source: "__root", target: catId, strength: catAvg / 100, kind: "root-cat" });

    kps.forEach((kp, ki) => {
      const spread = Math.max(kps.length - 1, 1);
      const localAngle = angle + ((ki - spread / 2) / spread) * 0.6;
      const x = cxCat + 110 * Math.cos(localAngle);
      const y = cyCat + 110 * Math.sin(localAngle);
      const kpId = `kp:${kp.name}`;
      const questions = kpToQuestions.get(kp.name) || [];
      nodes.push({
        id: kpId,
        label: kp.name,
        kind: "kp",
        r: radiusForKp(kp),
        x,
        y,
        score: kp.coverage_score,
        level: kp.level,
        planned: kp.planned_count,
        answered: kp.answered_count,
        avg: kp.avg_score,
        category: cat,
        questionIds: questions.map((q) => q.qid),
      });
      edges.push({ source: catId, target: kpId, strength: kp.coverage_score / 100, kind: "cat-kp" });
    });
  });

  const byScore = {
    excellent: items.filter((i) => i.coverage_score >= 80).length,
    good: items.filter((i) => i.coverage_score >= 60 && i.coverage_score < 80).length,
    fair: items.filter((i) => i.coverage_score >= 40 && i.coverage_score < 60).length,
    poor: items.filter((i) => i.coverage_score < 40).length,
  };

  return { nodes, edges, catAngle, kpToQuestions, byScore };
}

export function KnowledgeGraph({ coverage, perQuestion, position }: Props) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const simRef = useRef<Simulation<SimNode, SimEdge> | null>(null);
  const [tick, setTick] = useState(0);
  const [hover, setHover] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);
  const dragRef = useRef<{ id: string; offsetX: number; offsetY: number } | null>(null);

  const { nodes, edges, catAngle, kpToQuestions, byScore } = useMemo(
    () => buildGraph(coverage, perQuestion, position),
    [coverage, perQuestion, position],
  );

  const nodeIndex = useMemo(() => {
    const m = new Map<string, SimNode>();
    nodes.forEach((n) => m.set(n.id, n));
    return m;
  }, [nodes]);

  const startSimulation = useCallback(() => {
    if (simRef.current) simRef.current.stop();

    const sim = forceSimulation<SimNode>(nodes)
      .force(
        "link",
        forceLink<SimNode, SimEdge>(edges)
          .id((d) => d.id)
          .distance((e) => (e.kind === "root-cat" ? 150 : 95))
          .strength((e) => (e.kind === "root-cat" ? 0.85 : 0.45)),
      )
      .force("charge", forceManyBody().strength(-220))
      .force(
        "collide",
        forceCollide<SimNode>()
          .radius((d) => d.r + 14)
          .strength(0.95)
          .iterations(2),
      )
      .force("center", forceCenter(CX, CY).strength(0.04))
      .force(
        "radial-cat",
        forceRadial<SimNode>(
          (d) => (d.kind === "category" ? 160 : d.kind === "kp" ? 250 : 0),
          CX,
          CY,
        ).strength((d) => (d.kind === "root" ? 0 : d.kind === "category" ? 0.55 : 0.22)),
      )
      .force(
        "x-cluster",
        forceX<SimNode>((d) => {
          if (d.kind !== "kp" || !d.category) return CX;
          const a = catAngle.get(d.category) ?? 0;
          return CX + 250 * Math.cos(a);
        }).strength((d) => (d.kind === "kp" ? 0.18 : 0)),
      )
      .force(
        "y-cluster",
        forceY<SimNode>((d) => {
          if (d.kind !== "kp" || !d.category) return CY;
          const a = catAngle.get(d.category) ?? 0;
          return CY + 250 * Math.sin(a);
        }).strength((d) => (d.kind === "kp" ? 0.18 : 0)),
      )
      .alphaDecay(0.035)
      .velocityDecay(0.42);

    sim.on("tick", () => {
      const pad = 24;
      nodes.forEach((n) => {
        if (n.x == null || n.y == null) return;
        n.x = Math.max(n.r + pad, Math.min(W - n.r - pad, n.x));
        n.y = Math.max(n.r + pad, Math.min(H - n.r - pad, n.y));
      });
      setTick((t) => t + 1);
    });

    simRef.current = sim;
  }, [nodes, edges, catAngle]);

  useEffect(() => {
    startSimulation();
    return () => {
      simRef.current?.stop();
    };
  }, [startSimulation]);

  function clientToSvg(e: { clientX: number; clientY: number }) {
    const svg = svgRef.current;
    if (!svg) return { x: 0, y: 0 };
    const pt = svg.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const ctm = svg.getScreenCTM();
    if (!ctm) return { x: 0, y: 0 };
    const p = pt.matrixTransform(ctm.inverse());
    return { x: p.x, y: p.y };
  }

  function handlePointerDown(e: React.PointerEvent<SVGGElement>, node: SimNode) {
    if (node.kind === "root") return;
    (e.target as Element).setPointerCapture(e.pointerId);
    const { x, y } = clientToSvg(e);
    dragRef.current = { id: node.id, offsetX: (node.x ?? x) - x, offsetY: (node.y ?? y) - y };
    node.fx = node.x;
    node.fy = node.y;
    setPinned(node.id);
    simRef.current?.alphaTarget(0.25).restart();
  }

  function handlePointerMove(e: React.PointerEvent<SVGGElement>) {
    if (!dragRef.current) return;
    const node = nodeIndex.get(dragRef.current.id);
    if (!node) return;
    const { x, y } = clientToSvg(e);
    node.fx = x + dragRef.current.offsetX;
    node.fy = y + dragRef.current.offsetY;
  }

  function handlePointerUp(e: React.PointerEvent<SVGGElement>) {
    if (!dragRef.current) return;
    const node = nodeIndex.get(dragRef.current.id);
    if (node) {
      node.fx = node.fx;
      node.fy = node.fy;
    }
    dragRef.current = null;
    simRef.current?.alphaTarget(0);
  }

  function releasePin(id: string) {
    const node = nodeIndex.get(id);
    if (!node) return;
    node.fx = null;
    node.fy = null;
    setPinned((p) => (p === id ? null : p));
    simRef.current?.alpha(0.5).restart();
  }

  function resetLayout() {
    nodes.forEach((n) => {
      if (n.kind === "root") return;
      n.fx = null;
      n.fy = null;
    });
    setPinned(null);
    startSimulation();
    simRef.current?.alpha(1).restart();
  }

  const activeIds = useMemo(() => {
    if (!hover) return null;
    const ids = new Set<string>([hover]);
    edges.forEach((e) => {
      const sid = typeof e.source === "string" ? e.source : e.source.id;
      const tid = typeof e.target === "string" ? e.target : e.target.id;
      if (sid === hover) ids.add(tid);
      if (tid === hover) ids.add(sid);
    });
    return ids;
  }, [hover, edges]);

  const hoveredNode = hover ? nodeIndex.get(hover) : null;

  const overview = useMemo(() => {
    const items = (coverage.items || []) as KCItem[];
    const sorted = [...items].sort((a, b) => b.coverage_score - a.coverage_score);
    const top = sorted.slice(0, 3);
    const bottom = [...sorted].reverse().slice(0, 3);
    return { top, bottom };
  }, [coverage]);

  const pinnedNode = pinned ? nodeIndex.get(pinned) : null;
  const detail = hoveredNode || pinnedNode;

  return (
    <section className="glass-strong relative overflow-hidden rounded-2xl p-6">
      <div className="noise-layer rounded-2xl" />
      <div className="relative mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Network className="h-4 w-4 text-accent-cyan" />
            <h2 className="text-base font-medium">知识点图谱</h2>
          </div>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-ink-muted">
            围绕你的目标岗位铺开本场预设的所有知识点：圆圈越大权重越高，绿到红表示掌握到缺口。可以拖动任何节点重新排布，停在节点上能看到这道知识点出现在哪几道题里。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Legend byScore={byScore} />
          <button
            type="button"
            onClick={resetLayout}
            className="btn-soft tap-shrink inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs"
          >
            <RotateCw className="h-3.5 w-3.5" />
            重新布局
          </button>
        </div>
      </div>

      <div className="relative grid gap-5 lg:grid-cols-[1fr,260px]">
        <div className="relative overflow-hidden rounded-2xl border border-border bg-background/40">
          <svg
            ref={svgRef}
            viewBox={`0 0 ${W} ${H}`}
            role="img"
            aria-label="知识点掌握图谱"
            className="block w-full select-none touch-none"
            style={{ cursor: dragRef.current ? "grabbing" : "default" }}
            onMouseLeave={() => setHover(null)}
          >
            <defs>
              <radialGradient id="kg-root" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#a78bfa" stopOpacity="0.95" />
                <stop offset="60%" stopColor="#22d3ee" stopOpacity="0.85" />
                <stop offset="100%" stopColor="#0ea5e9" stopOpacity="0.6" />
              </radialGradient>
              <radialGradient id="kg-cat" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="rgba(255,255,255,0.18)" />
                <stop offset="100%" stopColor="rgba(167,139,250,0.05)" />
              </radialGradient>
              <filter id="kg-glow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="6" result="b" />
                <feMerge>
                  <feMergeNode in="b" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            {[110, 200, 290].map((r, i) => (
              <circle
                key={r}
                cx={CX}
                cy={CY}
                r={r}
                fill="none"
                stroke="rgba(148,163,184,0.08)"
                strokeDasharray={i === 1 ? "0" : "3 6"}
              />
            ))}

            {edges.map((edge, i) => {
              const source = typeof edge.source === "string" ? nodeIndex.get(edge.source) : edge.source;
              const target = typeof edge.target === "string" ? nodeIndex.get(edge.target) : edge.target;
              if (!source || !target || source.x == null || source.y == null || target.x == null || target.y == null)
                return null;
              const sid = source.id;
              const tid = target.id;
              const active = activeIds ? activeIds.has(sid) && activeIds.has(tid) : false;
              const dim = activeIds && !active;
              const tint = scoreTint(target.score ?? source.score);
              return (
                <line
                  key={`${sid}-${tid}-${i}`}
                  x1={source.x}
                  y1={source.y}
                  x2={target.x}
                  y2={target.y}
                  stroke={tint}
                  strokeWidth={active ? 2.4 : 1.1}
                  strokeOpacity={dim ? 0.08 : 0.3 + edge.strength * 0.5}
                />
              );
            })}

            {nodes.map((node, i) => {
              if (node.x == null || node.y == null) return null;
              const tint = scoreTint(node.score);
              const isHover = hover === node.id;
              const isPinned = pinned === node.id;
              const dim = activeIds && !activeIds.has(node.id);
              const baseOpacity = dim ? 0.2 : 1;
              const halo = node.r + (node.kind === "kp" ? 10 : 14);
              const fontSize = node.kind === "root" ? 13 : node.kind === "category" ? 12 : 10.5;
              const labelDy = node.kind === "root" ? 0 : node.r + 13;
              const cursor = node.kind === "root" ? "default" : "grab";
              return (
                <g
                  key={node.id}
                  style={{ opacity: baseOpacity, cursor }}
                  transform={`translate(${node.x},${node.y})`}
                  onMouseEnter={() => setHover(node.id)}
                  onMouseLeave={() => setHover((h) => (h === node.id ? null : h))}
                  onPointerDown={(e) => handlePointerDown(e, node)}
                  onPointerMove={handlePointerMove}
                  onPointerUp={handlePointerUp}
                  onPointerCancel={handlePointerUp}
                >
                  {(isHover || isPinned) && (
                    <circle r={halo} fill={tint} opacity={0.18} filter="url(#kg-glow)" />
                  )}
                  {isPinned && (
                    <circle r={node.r + 4} fill="none" stroke={tint} strokeWidth={1.5} strokeDasharray="4 4" opacity={0.7} />
                  )}
                  {node.kind === "root" ? (
                    <>
                      <circle r={node.r + 6} fill="rgba(167,139,250,0.18)" />
                      <circle r={node.r} fill="url(#kg-root)" stroke="rgba(255,255,255,0.4)" strokeWidth={1} />
                      <text textAnchor="middle" y={4} fontSize={fontSize} fontWeight={600} fill="white">
                        {trimLabel(node.label, 6)}
                      </text>
                    </>
                  ) : node.kind === "category" ? (
                    <>
                      <circle r={node.r} fill="url(#kg-cat)" stroke={tint} strokeWidth={1.5} strokeOpacity={0.75} />
                      <text textAnchor="middle" y={4} fontSize={fontSize} fontWeight={500} className="fill-ink">
                        {trimLabel(node.label, 5)}
                      </text>
                    </>
                  ) : (
                    <>
                      <circle r={node.r} fill={tint} fillOpacity={0.85} stroke="rgba(255,255,255,0.55)" strokeWidth={1} />
                      <text textAnchor="middle" y={labelDy} fontSize={fontSize} className="fill-ink" style={{ pointerEvents: "none" }}>
                        {trimLabel(node.label, 8)}
                      </text>
                    </>
                  )}
                </g>
              );
            })}
          </svg>

          <div className="pointer-events-none absolute bottom-3 left-4 flex items-center gap-1.5 text-[10px] text-ink-dim">
            <Hand className="h-3 w-3" />
            拖动节点能重新排布
          </div>
          {pinned && (
            <button
              onClick={() => releasePin(pinned)}
              className="absolute bottom-3 right-4 inline-flex items-center gap-1 rounded-full border border-border bg-surface/80 px-2.5 py-1 text-[10px] text-ink-muted backdrop-blur transition hover:text-ink"
            >
              <Move className="h-3 w-3" />
              松开 {trimLabel(nodeIndex.get(pinned)?.label ?? "", 6)}
            </button>
          )}
        </div>

        <aside className="space-y-4">
          {detail ? (
            <DetailPanel
              node={detail}
              questionsForKp={detail.kind === "kp" ? kpToQuestions.get(detail.label) || [] : []}
              perQuestion={perQuestion}
            />
          ) : (
            <Overview top={overview.top} bottom={overview.bottom} />
          )}
        </aside>
      </div>
    </section>
  );
}

function DetailPanel({
  node,
  questionsForKp,
  perQuestion,
}: {
  node: SimNode;
  questionsForKp: { qid: string; category: string; score: number }[];
  perQuestion: PerQ[];
}) {
  const tint = scoreTint(node.score);
  if (node.kind === "category") {
    return (
      <div className="glass-strong relative overflow-hidden rounded-2xl border border-border p-4">
        <div className="flex items-center gap-2">
          <Sparkles className="h-3.5 w-3.5 text-accent-cyan" />
          <span className="text-sm font-medium text-ink">{node.label}</span>
        </div>
        <div className="mt-1 text-xs text-ink-dim">方向均分</div>
        <div className="mt-1 flex items-baseline gap-2">
          <span className="font-mono text-3xl text-ink">{node.score ?? "--"}</span>
          <span className="text-xs" style={{ color: tint }}>
            {scoreLabel(node.score)}
          </span>
        </div>
        <p className="mt-3 text-xs leading-relaxed text-ink-muted">
          鼠标停在外圈节点上可以看每个知识点的得分与所属题目。
        </p>
      </div>
    );
  }

  if (node.kind === "kp") {
    const detailedQs = questionsForKp.map((q) => {
      const full = perQuestion.find((p) => p.id === q.qid);
      return {
        ...q,
        gaps: full?.gaps || "",
        rubricFollow: full?.rubric_scores?.knowledge?.score,
      };
    });
    const coveragePct = node.planned && node.planned > 0 ? Math.round(((node.answered || 0) / node.planned) * 100) : 0;
    return (
      <div className="glass-strong relative overflow-hidden rounded-2xl border border-border p-4">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: tint }} />
          <span className="text-sm font-medium text-ink">{node.label}</span>
        </div>
        <div className="mt-0.5 text-xs text-ink-dim">
          {node.category} · {node.level || scoreLabel(node.score)}
        </div>
        <div className="mt-3 grid grid-cols-3 gap-2">
          <Stat label="掌握" value={node.score} accent={tint} />
          <Stat label="均分" value={node.avg} />
          <Stat label="覆盖" value={`${node.answered ?? 0}/${node.planned ?? 0}`} />
        </div>
        <div className="mt-3">
          <div className="mb-1 flex items-center justify-between text-[10px] text-ink-dim">
            <span>覆盖率</span>
            <span className="font-mono text-ink">{coveragePct}%</span>
          </div>
          <div className="progress-track h-1.5 overflow-hidden rounded-full">
            <div className="h-full rounded-full" style={{ width: `${coveragePct}%`, background: `linear-gradient(90deg, ${tint}, ${PALETTE.neutral})` }} />
          </div>
        </div>
        {detailedQs.length > 0 && (
          <div className="mt-4">
            <div className="mb-2 flex items-center gap-1 text-[10px] uppercase tracking-wider text-ink-dim">
              <Target className="h-3 w-3" />
              出现在
            </div>
            <ul className="space-y-2">
              {detailedQs.map((q) => (
                <li key={q.qid} className="rounded-lg border border-border bg-surface px-2.5 py-2">
                  <div className="flex items-center justify-between gap-2 text-xs">
                    <span className="font-mono text-ink-muted">{q.qid}</span>
                    <span className="truncate text-ink-dim" title={q.category}>{q.category}</span>
                    <span className="font-mono" style={{ color: scoreTint(q.score) }}>{q.score}</span>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  }

  return null;
}

function Overview({ top, bottom }: { top: KCItem[]; bottom: KCItem[] }) {
  return (
    <div className="space-y-3">
      <SummaryCard title="掌握得最好" items={top} accent={PALETTE.excellent} />
      <SummaryCard title="还需要补的" items={bottom} accent={PALETTE.poor} />
      <div className="glass-strong rounded-2xl border border-border p-3 text-[11px] leading-relaxed text-ink-dim">
        <Hand className="mr-1 inline h-3 w-3" />
        把任意节点拖到舒服的位置；松开后它会停在那里。点「重新布局」可以把所有节点放回去。
      </div>
    </div>
  );
}

function SummaryCard({ title, items, accent }: { title: string; items: KCItem[]; accent: string }) {
  return (
    <div className="glass-strong rounded-2xl border border-border p-3">
      <div className="mb-2 flex items-center gap-1.5 text-xs text-ink-muted">
        <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: accent }} />
        {title}
      </div>
      <ul className="space-y-1.5">
        {items.map((item) => (
          <li key={item.name} className="flex items-center justify-between gap-2 text-xs">
            <span className="truncate text-ink">{item.name}</span>
            <span className="font-mono" style={{ color: scoreTint(item.coverage_score) }}>
              {item.coverage_score}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value?: number | string | null; accent?: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface px-2 py-1.5 text-center">
      <div className="text-[10px] uppercase tracking-wider text-ink-dim">{label}</div>
      <div className="mt-0.5 font-mono text-sm" style={{ color: accent || "var(--app-fg)" }}>
        {value == null ? "--" : value}
      </div>
    </div>
  );
}

function Legend({ byScore }: { byScore: { excellent: number; good: number; fair: number; poor: number } }) {
  const items: { label: string; color: string; count: number }[] = [
    { label: "掌握", color: PALETTE.excellent, count: byScore.excellent },
    { label: "熟悉", color: PALETTE.good, count: byScore.good },
    { label: "薄弱", color: PALETTE.fair, count: byScore.fair },
    { label: "缺口", color: PALETTE.poor, count: byScore.poor },
  ];
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-ink-muted">
      {items.map((item) => (
        <span
          key={item.label}
          className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1"
        >
          <span className="h-2 w-2 rounded-full" style={{ backgroundColor: item.color }} />
          {item.label}
          <span className="font-mono text-ink">{item.count}</span>
        </span>
      ))}
    </div>
  );
}

function trimLabel(s: string, max: number) {
  return s.length > max ? `${s.slice(0, max)}…` : s;
}
