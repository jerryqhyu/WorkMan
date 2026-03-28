import { invoke } from '@tauri-apps/api/core'

let runtimeBase = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8765'

function isTauri(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
}

export async function ensureDesktopBackend(): Promise<string> {
  if (isTauri()) {
    try {
      runtimeBase = await invoke<string>('ensure_backend')
    } catch (error) {
      console.warn('Failed to auto-start backend', error)
    }
  }
  return runtimeBase
}

export function apiBase(): string {
  return runtimeBase
}

export function wsBase(): string {
  return runtimeBase.replace('http://', 'ws://').replace('https://', 'wss://')
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${runtimeBase}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {})
    },
    ...init
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) => request<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) => request<T>(path, { method: 'PATCH', body: JSON.stringify(body) })
}
