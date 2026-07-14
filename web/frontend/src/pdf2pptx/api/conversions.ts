import type { ConversionAcceptedResponse, JobStatusResponse } from '../types/conversion'

// Relative path deliberately -- works unchanged both under the Vite dev-server
// proxy (local dev) and the nginx reverse proxy (Docker/production), no
// per-environment branching needed here.
const API_BASE = '/api'

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function parseErrorMessage(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { error?: unknown }
    if (typeof body?.error === 'string') return body.error
  }
  catch {
    // response wasn't JSON (or had no body) -- fall through to a generic message
  }
  return `要求失敗（狀態碼 ${res.status}）`
}

export async function submitConversion(file: File): Promise<ConversionAcceptedResponse> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${API_BASE}/conversions`, { method: 'POST', body: form })
  if (!res.ok) throw new ApiError(res.status, await parseErrorMessage(res))
  return (await res.json()) as ConversionAcceptedResponse
}

export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  const res = await fetch(`${API_BASE}/conversions/${encodeURIComponent(jobId)}`)
  if (!res.ok) throw new ApiError(res.status, await parseErrorMessage(res))
  return (await res.json()) as JobStatusResponse
}

export function resultDownloadUrl(jobId: string): string {
  return `${API_BASE}/conversions/${encodeURIComponent(jobId)}/result`
}
