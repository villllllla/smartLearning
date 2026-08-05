import { api } from "./client";
import type { PracticeSetupResponse } from "./practice";

export interface JobRoleSkill {
  id: number;
  skill_name: string;
  tag_name: string;
  weight: number;
  expected_mastery: number;
}

export interface JobRole {
  id: number;
  name: string;
  family: string;
  level: string;
  description: string;
  is_system: boolean;
  skills: JobRoleSkill[];
}

export interface UserGoal {
  id: number;
  job_role_id: number;
  job_role_name: string;
  target_date: string | null;
  status: "active" | "achieved" | "archived";
  created_at: string;
}

export interface SkillProgress {
  skill_name: string;
  tag_name: string;
  tag_id: number | null;
  weight: number;
  expected_mastery: number;
  mastery: number;
  question_total: number;
  question_attempted: number;
  coverage: number;
  low_coverage: boolean;
}

export interface WeakTag {
  tag_name: string;
  tag_id: number | null;
  mastery: number;
  expected_mastery: number;
  gap: number;
}

export interface GoalProgress {
  goal: UserGoal;
  overall_mastery: number;
  skills: SkillProgress[];
  weak_tags: WeakTag[];
  trend: Array<{ computed_at: string; overall_mastery: number }>;
  coverage_note: string | null;
}

export const goalsApi = {
  listJobRoles: (q?: string) =>
    api.get<JobRole[]>(`/goals/job-roles${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  createJobRole: (body: {
    name: string;
    family?: string;
    level?: string;
    description?: string;
    skills?: Array<{ skill_name: string; tag_name: string; weight?: number }>;
  }) => api.post<JobRole>("/goals/job-roles", body),
  list: (status?: string) =>
    api.get<UserGoal[]>(`/goals${status ? `?status=${status}` : ""}`),
  getActive: () => api.get<UserGoal | null>("/goals/active"),
  get: (id: number) => api.get<UserGoal>(`/goals/${id}`),
  create: (body: { job_role_id: number; target_date?: string | null }) =>
    api.post<UserGoal>("/goals", body),
  update: (
    id: number,
    body: {
      job_role_id?: number;
      target_date?: string | null;
      status?: UserGoal["status"];
      clear_target_date?: boolean;
    },
  ) => api.patch<UserGoal>(`/goals/${id}`, body),
  remove: (id: number) => api.delete<void>(`/goals/${id}`),
  progress: (id: number) => api.get<GoalProgress>(`/goals/${id}/progress`),
  recommendPractice: (id: number) =>
    api.post<PracticeSetupResponse>(`/goals/${id}/recommend-practice`),
};
