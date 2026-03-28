export type Project = {
  id: string
  name: string
  repo_path: string
  repo_url?: string | null
  default_branch: string
  metadata_json: Record<string, unknown>
  created_at: string
  updated_at: string
}

export type FeatureMessage = {
  id: string
  role: string
  content: string
  created_at: string
}

export type Task = {
  id: string
  feature_id: string
  planning_key: string
  title: string
  description: string
  status: string
  priority: number
  acceptance_criteria: string[]
  labels: string[]
  auto_execute: boolean
  archived: boolean
  branch_name?: string | null
  worktree_path?: string | null
  latest_run_id?: string | null
  depends_on: string[]
  created_at: string
  updated_at: string
}

export type DocumentRecord = {
  id: string
  kind: string
  path: string
  content: string
  updated_at: string
}

export type Feature = {
  id: string
  project_id: string
  title: string
  goal: string
  status: string
  summary: string
  acceptance_criteria: string[]
  auto_execute: boolean
  needs_replan: boolean
  last_planned_at?: string | null
  created_at: string
  updated_at: string
  messages: FeatureMessage[]
  tasks: Task[]
  documents: DocumentRecord[]
}

export type RunEvent = {
  id: string
  run_id: string
  feature_id: string
  event_type: string
  level: string
  message: string
  payload: Record<string, unknown>
  created_at: string
}

export type Run = {
  id: string
  project_id: string
  feature_id: string
  task_id: string
  provider: string
  status: string
  branch_name?: string | null
  worktree_path?: string | null
  session_id?: string | null
  pr_url?: string | null
  result_summary: string
  result_json: Record<string, unknown>
  error?: string | null
  started_at?: string | null
  ended_at?: string | null
  created_at: string
  events: RunEvent[]
}
