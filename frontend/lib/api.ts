export interface PlannedQuestion {
  id: string;
  category: string;
  intent?: string;
  knowledge_points?: string[];
  question?: string;
}

export interface ResumeProfile {
  name?: string;
  years_of_experience?: number;
  current_title?: string;
  skills?: string[];
  projects?: { name?: string; role?: string; highlight?: string }[];
  highlights?: string[];
}

export interface SessionSnapshot {
  session_id: string;
  profile?: ResumeProfile;
  question_plan: PlannedQuestion[];
  pending_question: string;
  pending_kind: "main" | "follow_up";
  current_q_index: number;
  total_questions: number;
  stage: string;
  qa_history?: QAHistoryItem[];
  agents: string[];
  last_active_agent?: string;
}

const USER_KEY = "aurora_user_id";
const TOKEN_KEY = "aurora_auth_token";
const USER_PROFILE_KEY = "aurora_user_profile";

export interface AuthUser {
  id: string;
  email: string;
  display_name: string;
}

export interface AuthResponse {
  token: string;
  user: AuthUser;
}

export interface InterviewRecord {
  session_id: string;
  position: string;
  stage: string;
  candidate: string;
  score?: number;
  recommendation?: string;
  created_at: string;
  updated_at: string;
  report_ready: boolean;
}

export function getLocalUserId(): string {
  if (typeof window === "undefined") return "";
  let id = window.localStorage.getItem(USER_KEY);
  if (!id) {
    id = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);
    window.localStorage.setItem(USER_KEY, id);
  }
  return id;
}

export async function ensureUser(displayName?: string): Promise<{ id: string; display_name: string }> {
  const userId = getLocalUserId();
  const res = await fetch(`${API_BASE}/api/users/ensure`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, display_name: displayName }),
  });
  return handle(res);
}

export function getAuthToken(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(TOKEN_KEY) || "";
}

export function getStoredUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(USER_PROFILE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

function saveAuth(auth: AuthResponse): AuthResponse {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(TOKEN_KEY, auth.token);
    window.localStorage.setItem(USER_PROFILE_KEY, JSON.stringify(auth.user));
  }
  return auth;
}

export function clearAuth() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_PROFILE_KEY);
}

function authHeaders(): Record<string, string> {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function register(email: string, password: string, displayName?: string): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, display_name: displayName }),
  });
  return saveAuth(await handle<AuthResponse>(res));
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return saveAuth(await handle<AuthResponse>(res));
}

export async function getMe(): Promise<AuthUser> {
  const res = await fetch(`${API_BASE}/api/auth/me`, { headers: authHeaders() });
  return handle<AuthUser>(res);
}

export async function logout(): Promise<void> {
  const token = getAuthToken();
  if (token) {
    await fetch(`${API_BASE}/api/auth/logout`, {
      method: "POST",
      headers: authHeaders(),
    }).catch(() => undefined);
  }
  clearAuth();
}

export interface AnswerResponse {
  pending_question: string;
  pending_kind: "main" | "follow_up";
  question_plan?: PlannedQuestion[];
  current_q_index: number;
  total_questions: number;
  stage: string;
  last_active_agent?: string;
  done: boolean;
}

export interface SpeechMetrics {
  source: "browser_asr";
  duration_ms: number;
  confidence?: number;
  transcript_length: number;
  interim_updates?: number;
  final_segments?: number;
  avg_volume?: number;
  peak_volume?: number;
  silence_rate?: number;
  volume_stability?: number;
  volume_variability?: number;
}

export interface QAHistoryItem {
  q_id: string;
  category: string;
  intent?: string;
  knowledge_points?: string[];
  question: string;
  answer: string;
  skipped?: boolean;
  speech_metrics?: SpeechMetrics;
  follow_ups: { question: string; answer: string; skipped?: boolean; speech_metrics?: SpeechMetrics }[];
}

export interface DimensionDetail {
  name: string;
  score: number;
  level: string;
  evidence_count: number;
  skipped_count: number;
  insight: string;
}

export interface RiskFlag {
  level: "high" | "medium" | "low" | string;
  title: string;
  detail: string;
}

export interface SignalDimension {
  name: string;
  score?: number | null;
  level: string;
  insight: string;
}

export interface FinalReport {
  overall_score: number;
  recommendation: "强烈推荐" | "推荐" | "待定" | "不推荐" | string;
  summary: string;
  strengths: string[];
  gaps: string[];
  next_steps: string[];
  risk_flags?: RiskFlag[];
  completion?: {
    answered: number;
    skipped: number;
    total_seen: number;
    target_total?: number;
    follow_ups: number;
    completion_rate?: number;
  };
  communication_analysis?: {
    text: string;
    audio: string;
    video?: string;
    metrics?: {
      voice_answer_count: number;
      audio_sample_count?: number;
      avg_duration_seconds?: number;
      avg_confidence?: number;
      avg_words_per_minute?: number;
      avg_volume?: number;
      peak_volume?: number;
      silence_rate?: number;
      volume_stability?: number;
      fluency_score?: number;
      nervousness_score?: number;
      confidence_score?: number;
      pace_label?: string;
    };
    video_metrics?: {
      sample_count: number;
      presence_rate?: number;
      avg_brightness?: number;
      avg_motion_proxy?: number;
      avg_face_count?: number;
      avg_attention_score?: number;
      center_rate?: number;
      lighting_quality?: string;
      motion_quality?: string;
      visual_nervousness_score?: number;
      presence_score?: number;
      framing_score?: number;
      lighting_score?: number;
    };
    audio_dimensions?: SignalDimension[];
    video_dimensions?: SignalDimension[];
  };
  dimensions: Record<string, number>;
  dimension_details?: DimensionDetail[];
  interview_trace?: {
    main_questions_seen: number;
    evaluated_questions: number;
    skipped_questions: number;
    follow_up_answers: number;
    categories_seen: string[];
  };
  per_question: {
    id: string;
    category: string;
    knowledge_points?: string[];
    covered_knowledge_points?: string[];
    score: number;
    strengths: string;
    gaps: string;
    rubric_scores?: Record<string, { label?: string; score?: number; weight?: number }>;
    evidence_quality?: number;
    uncertainty?: number;
    evaluation_notes?: string[];
  }[];
  qa_history: QAHistoryItem[];
  knowledge_coverage?: {
    overall_score: number;
    coverage_rate: number;
    planned_points: number;
    answered_points: number;
    summary: string;
    items: {
      name: string;
      planned_count: number;
      answered_count: number;
      coverage_rate: number;
      avg_score: number;
      coverage_score: number;
      level: string;
    }[];
    strongest?: { name: string; coverage_score: number; level: string }[];
    weakest?: { name: string; coverage_score: number; level: string }[];
  };
  evaluation_methodology?: {
    name: string;
    version: string;
    summary: string;
    principles: string[];
    calibration?: {
      avg_evidence_quality?: number;
      avg_uncertainty?: number;
      completion_rate?: number;
      knowledge_score?: number;
    };
  };
  profile?: ResumeProfile;
  position: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";

async function fetchWithTimeout(url: string, init: RequestInit = {}, timeoutMs = 45000): Promise<Response> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (err: any) {
    if (err?.name === "AbortError") {
      throw new Error("请求超时，请稍后重试。当前回答已尽量保存在本地会话中。");
    }
    throw err;
  } finally {
    window.clearTimeout(timer);
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    let message = text || `请求失败 ${res.status}`;
    try {
      const data = JSON.parse(text);
      message = data.detail || message;
    } catch (err) {
      // Keep the raw response text when it is not JSON.
    }
    throw new Error(message);
  }
  return res.json();
}

export async function createSession(
  file: File,
  position: string,
  difficulty: string,
): Promise<SessionSnapshot> {
  const form = new FormData();
  form.append("resume", file);
  form.append("position", position);
  form.append("difficulty", difficulty);
  form.append("user_id", getLocalUserId());
  const res = await fetch(`${API_BASE}/api/sessions`, { method: "POST", body: form, headers: authHeaders() });
  return handle<SessionSnapshot>(res);
}

export async function getSession(id: string): Promise<SessionSnapshot> {
  const res = await fetch(`${API_BASE}/api/sessions/${id}`);
  return handle<SessionSnapshot>(res);
}

export async function submitAnswer(
  id: string,
  answer: string,
  speechMetrics?: SpeechMetrics,
): Promise<AnswerResponse> {
  const res = await fetchWithTimeout(`${API_BASE}/api/sessions/${id}/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answer, speech_metrics: speechMetrics }),
  }, 30000);
  return handle<AnswerResponse>(res);
}

export async function skipQuestion(id: string): Promise<AnswerResponse> {
  const res = await fetchWithTimeout(`${API_BASE}/api/sessions/${id}/skip`, {
    method: "POST",
  }, 30000);
  return handle<AnswerResponse>(res);
}

export async function finalize(id: string): Promise<{ report_ready: boolean }> {
  const res = await fetchWithTimeout(`${API_BASE}/api/sessions/${id}/finalize`, { method: "POST" }, 180000);
  return handle(res);
}

export async function getReport(id: string): Promise<FinalReport> {
  const res = await fetch(`${API_BASE}/api/report/${id}`);
  return handle<FinalReport>(res);
}

export async function listMySessions(): Promise<InterviewRecord[]> {
  const res = await fetch(`${API_BASE}/api/users/me/sessions`, { headers: authHeaders() });
  const data = await handle<{ items: InterviewRecord[] }>(res);
  return data.items;
}

export async function recordAnalytics(
  id: string,
  kind: "video" | "audio",
  payload: Record<string, unknown>,
): Promise<void> {
  await fetch(`${API_BASE}/api/sessions/${id}/analytics`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, payload }),
  });
}
