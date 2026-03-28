import { FormEvent, useEffect, useMemo, useState } from 'react'

import { api, ensureDesktopBackend, wsBase } from './api'
import { Feature, Project, Run, Task } from './types'

const featureColumns = ['draft', 'planning', 'ready', 'active', 'review', 'done', 'blocked']
const taskColumns = ['backlog', 'ready', 'leased', 'implementing', 'review', 'done', 'blocked']

function groupByStatus<T extends { status: string }>(items: T[], columns: string[]) {
  return Object.fromEntries(columns.map((column) => [column, items.filter((item) => item.status === column)])) as Record<string, T[]>
}

function formatTime(value?: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}

export default function App() {
  const [projects, setProjects] = useState<Project[]>([])
  const [features, setFeatures] = useState<Feature[]>([])
  const [runs, setRuns] = useState<Run[]>([])
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)
  const [selectedFeatureId, setSelectedFeatureId] = useState<string | null>(null)
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [projectPath, setProjectPath] = useState('')
  const [featureTitle, setFeatureTitle] = useState('')
  const [featureGoal, setFeatureGoal] = useState('')
  const [chatInput, setChatInput] = useState('')
  const [view, setView] = useState<'features' | 'tasks' | 'runs'>('features')
  const [error, setError] = useState<string | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    ensureDesktopBackend().finally(() => setReady(true))
  }, [])

  const selectedFeature = useMemo(
    () => features.find((feature) => feature.id === selectedFeatureId) ?? features[0] ?? null,
    [features, selectedFeatureId]
  )
  const selectedRun = useMemo(
    () => runs.find((run) => run.id === selectedRunId) ?? runs[0] ?? null,
    [runs, selectedRunId]
  )
  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId) ?? projects[0] ?? null,
    [projects, selectedProjectId]
  )

  async function refreshProjects() {
    const nextProjects = await api.get<Project[]>('/projects')
    setProjects(nextProjects)
    if (!selectedProjectId && nextProjects[0]) {
      setSelectedProjectId(nextProjects[0].id)
    }
  }

  async function refreshProjectState(projectId: string) {
    const nextFeatures = await api.get<Feature[]>(`/projects/${projectId}/features`)
    setFeatures(nextFeatures)
    const preferredFeature = nextFeatures.find((item) => item.id === selectedFeatureId) ?? nextFeatures[0] ?? null
    if (preferredFeature) {
      setSelectedFeatureId(preferredFeature.id)
      const nextRuns = await api.get<Run[]>(`/features/${preferredFeature.id}/runs`)
      setRuns(nextRuns)
      if (!selectedRunId && nextRuns[0]) {
        setSelectedRunId(nextRuns[0].id)
      }
    } else {
      setRuns([])
      setSelectedFeatureId(null)
      setSelectedRunId(null)
    }
  }

  useEffect(() => {
    if (!ready) return
    refreshProjects().catch((err) => setError(String(err)))
  }, [ready])

  useEffect(() => {
    if (!ready || !selectedProjectId) return
    refreshProjectState(selectedProjectId).catch((err) => setError(String(err)))
    const interval = window.setInterval(() => {
      refreshProjectState(selectedProjectId).catch((err) => setError(String(err)))
    }, 5000)
    return () => window.clearInterval(interval)
  }, [ready, selectedProjectId, selectedFeatureId])

  useEffect(() => {
    if (!ready) return
    const socket = new WebSocket(`${wsBase()}/ws`)
    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)
        if (message.type?.startsWith('run.') || message.type?.startsWith('feature.')) {
          if (selectedProjectId) {
            refreshProjectState(selectedProjectId).catch((err) => setError(String(err)))
          }
        }
      } catch {
        // ignore
      }
    }
    socket.onopen = () => socket.send('subscribe')
    return () => socket.close()
  }, [ready, selectedProjectId])

  async function importProject(event: FormEvent) {
    event.preventDefault()
    if (!projectPath.trim()) return
    try {
      await api.post('/projects/import', { repo_path: projectPath.trim() })
      setProjectPath('')
      await refreshProjects()
    } catch (err) {
      setError(String(err))
    }
  }

  async function createFeature(event: FormEvent) {
    event.preventDefault()
    if (!selectedProject || !featureTitle.trim() || !featureGoal.trim()) return
    try {
      const response = await api.post<{ feature_id: string }>(`/projects/${selectedProject.id}/features`, {
        title: featureTitle.trim(),
        goal: featureGoal.trim(),
        acceptance_criteria: [],
        auto_execute: true
      })
      setFeatureTitle('')
      setFeatureGoal('')
      await refreshProjectState(selectedProject.id)
      setSelectedFeatureId(response.feature_id)
    } catch (err) {
      setError(String(err))
    }
  }

  async function sendFeatureMessage(event: FormEvent) {
    event.preventDefault()
    if (!selectedFeature || !chatInput.trim()) return
    try {
      await api.post(`/features/${selectedFeature.id}/chat`, { message: chatInput.trim() })
      setChatInput('')
      await refreshProjectState(selectedFeature.project_id)
    } catch (err) {
      setError(String(err))
    }
  }

  async function spawnTask(taskId: string) {
    try {
      const response = await api.post<{ run_id: string | null }>(`/tasks/${taskId}/spawn`, {})
      if (response.run_id) setSelectedRunId(response.run_id)
      if (selectedProjectId) {
        await refreshProjectState(selectedProjectId)
      }
      setView('runs')
    } catch (err) {
      setError(String(err))
    }
  }

  async function setTaskStatus(task: Task, status: string) {
    try {
      await api.patch(`/tasks/${task.id}`, { status })
      if (selectedProjectId) {
        await refreshProjectState(selectedProjectId)
      }
    } catch (err) {
      setError(String(err))
    }
  }

  const featureBoard = groupByStatus(features, featureColumns)
  const taskBoard = groupByStatus(selectedFeature?.tasks ?? [], taskColumns)

  return (
    <div className="window-shell">
      <aside className="sidebar">
        <div className="titlebar drag-region">
          <div className="traffic-lights">
            <span className="traffic red" />
            <span className="traffic yellow" />
            <span className="traffic green" />
          </div>
          <div>
            <div className="app-title">AgentPM</div>
            <div className="app-subtitle">Local control plane for Claude Code teams</div>
          </div>
        </div>

        <form className="panel compact-panel" onSubmit={importProject}>
          <label className="panel-label">Import Git repository</label>
          <input value={projectPath} onChange={(event) => setProjectPath(event.target.value)} placeholder="/Users/you/dev/project" />
          <button type="submit">Import repo</button>
        </form>

        <div className="panel list-panel">
          <div className="panel-heading">Projects</div>
          <div className="stack">
            {projects.map((project) => (
              <button
                key={project.id}
                className={`list-item ${selectedProject?.id === project.id ? 'active' : ''}`}
                onClick={() => {
                  setSelectedProjectId(project.id)
                  setSelectedFeatureId(null)
                  setSelectedRunId(null)
                }}
              >
                <div className="list-item-title">{project.name}</div>
                <div className="list-item-subtitle">{project.default_branch} · {project.repo_path}</div>
              </button>
            ))}
          </div>
        </div>

        <form className="panel compact-panel" onSubmit={createFeature}>
          <label className="panel-label">New feature</label>
          <input value={featureTitle} onChange={(event) => setFeatureTitle(event.target.value)} placeholder="Feature title" />
          <textarea value={featureGoal} onChange={(event) => setFeatureGoal(event.target.value)} placeholder="Describe the goal, constraints, and desired behavior" />
          <button type="submit" disabled={!selectedProject}>Create feature</button>
        </form>
      </aside>

      <main className="main-pane">
        <header className="toolbar drag-region">
          <div>
            <div className="toolbar-title">{selectedProject?.name ?? 'No project selected'}</div>
            <div className="toolbar-subtitle">{selectedProject?.repo_path ?? 'Import a local git repository to begin.'}</div>
          </div>
          <div className="segmented-control no-drag">
            {(['features', 'tasks', 'runs'] as const).map((segment) => (
              <button key={segment} className={view === segment ? 'active' : ''} onClick={() => setView(segment)}>
                {segment}
              </button>
            ))}
          </div>
        </header>

        {error ? <div className="banner error">{error}</div> : null}

        {view === 'features' ? (
          <section className="board-grid">
            {featureColumns.map((column) => (
              <div key={column} className="board-column">
                <div className="board-column-header">{column}</div>
                <div className="board-column-body">
                  {featureBoard[column].map((feature) => (
                    <button
                      key={feature.id}
                      className={`board-card ${selectedFeature?.id === feature.id ? 'selected' : ''}`}
                      onClick={() => {
                        setSelectedFeatureId(feature.id)
                        setView('tasks')
                      }}
                    >
                      <div className="card-title">{feature.title}</div>
                      <div className="card-body">{feature.summary || feature.goal}</div>
                      <div className="card-meta">{feature.tasks.length} tasks</div>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </section>
        ) : null}

        {view === 'tasks' ? (
          <section className="board-grid">
            {taskColumns.map((column) => (
              <div key={column} className="board-column">
                <div className="board-column-header">{column}</div>
                <div className="board-column-body">
                  {taskBoard[column].map((task) => (
                    <div key={task.id} className="board-card task-card">
                      <div className="card-title">{task.title}</div>
                      <div className="card-chip-row">
                        {task.labels.map((label) => (
                          <span key={label} className="chip">{label}</span>
                        ))}
                      </div>
                      <div className="card-body">{task.description}</div>
                      <div className="card-meta">depends on: {task.depends_on.join(', ') || 'none'}</div>
                      <div className="card-actions">
                        <button onClick={() => spawnTask(task.id)}>Run</button>
                        <button className="secondary" onClick={() => setTaskStatus(task, 'done')}>Mark done</button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </section>
        ) : null}

        {view === 'runs' ? (
          <section className="run-list">
            {runs.map((run) => (
              <button key={run.id} className={`run-row ${selectedRun?.id === run.id ? 'active' : ''}`} onClick={() => setSelectedRunId(run.id)}>
                <div>
                  <div className="run-row-title">{run.provider} · {run.status}</div>
                  <div className="run-row-subtitle">{run.branch_name || 'branch pending'} · {formatTime(run.started_at)}</div>
                </div>
                <div className="run-row-right">{run.pr_url ? 'PR' : 'Local'}</div>
              </button>
            ))}
          </section>
        ) : null}
      </main>

      <aside className="inspector">
        <section className="panel inspector-panel">
          <div className="panel-heading">Feature detail</div>
          {selectedFeature ? (
            <>
              <div className="detail-title">{selectedFeature.title}</div>
              <div className="detail-meta">status: {selectedFeature.status} · planned: {formatTime(selectedFeature.last_planned_at)}</div>
              <p className="detail-copy">{selectedFeature.goal}</p>
              <div className="detail-section">
                <div className="detail-section-title">Acceptance criteria</div>
                <ul>
                  {selectedFeature.acceptance_criteria.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
              <div className="detail-section">
                <div className="detail-section-title">Living docs</div>
                {(selectedFeature.documents.length ? selectedFeature.documents : []).map((document) => (
                  <details key={document.id} className="doc-block">
                    <summary>{document.path}</summary>
                    <pre>{document.content}</pre>
                  </details>
                ))}
              </div>
            </>
          ) : (
            <div className="empty-state">Select or create a feature to inspect it.</div>
          )}
        </section>

        <section className="panel inspector-panel chat-panel">
          <div className="panel-heading">Master-agent chat</div>
          <div className="chat-transcript">
            {selectedFeature?.messages.map((message) => (
              <div key={message.id} className={`chat-message ${message.role}`}>
                <div className="chat-role">{message.role}</div>
                <div className="chat-content">{message.content}</div>
              </div>
            )) ?? <div className="empty-state">Feature conversation will appear here.</div>}
          </div>
          <form className="chat-compose" onSubmit={sendFeatureMessage}>
            <textarea value={chatInput} onChange={(event) => setChatInput(event.target.value)} placeholder="Describe the next change, ask for re-planning, or add constraints." />
            <button type="submit" disabled={!selectedFeature}>Send</button>
          </form>
        </section>

        <section className="panel inspector-panel run-panel">
          <div className="panel-heading">Selected run</div>
          {selectedRun ? (
            <>
              <div className="detail-title">{selectedRun.branch_name || selectedRun.id}</div>
              <div className="detail-meta">{selectedRun.status} · {selectedRun.provider}</div>
              {selectedRun.pr_url ? <a href={selectedRun.pr_url} target="_blank" rel="noreferrer">Open draft PR</a> : null}
              <pre className="run-summary">{selectedRun.result_summary || 'Run has not completed yet.'}</pre>
              <div className="event-log">
                {selectedRun.events.map((event) => (
                  <div key={event.id} className={`event-row ${event.level}`}>
                    <div className="event-type">{event.event_type}</div>
                    <div className="event-message">{event.message}</div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="empty-state">Spawn a task run to inspect its event stream.</div>
          )}
        </section>
      </aside>
    </div>
  )
}
