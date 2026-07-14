import { ApiError, parseErrorMessage } from './conversions'

const API_BASE = '/api'

export interface ApiSlide {
  id: string
  pageIndex: number
  sourceWidth: number
  sourceHeight: number
  backgroundImage: string
  originalImage: string
  // Already PPTist PPTTextElement-shaped JSON, forwarded verbatim by the
  // backend -- see service/pptist.py and web/backend's SlideDto.
  elements: Record<string, unknown>[]
}

export interface SlidesResponse {
  viewportRatio: number
  slides: ApiSlide[]
}

export interface BackgroundImageResponse {
  backgroundImage: string
}

export async function getSlides(jobId: string): Promise<SlidesResponse> {
  const res = await fetch(`${API_BASE}/conversions/${encodeURIComponent(jobId)}/slides`)
  if (!res.ok) throw new ApiError(res.status, await parseErrorMessage(res))
  return (await res.json()) as SlidesResponse
}

export type InpaintSource = 'original' | 'current'

export async function inpaintRegion(
  jobId: string,
  pageIndex: number,
  points: [number, number][],
  source: InpaintSource,
): Promise<BackgroundImageResponse> {
  const res = await fetch(`${API_BASE}/conversions/${encodeURIComponent(jobId)}/pages/${pageIndex}/inpaint`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ points, source }),
  })
  if (!res.ok) throw new ApiError(res.status, await parseErrorMessage(res))
  return (await res.json()) as BackgroundImageResponse
}

export async function revertPage(jobId: string, pageIndex: number): Promise<BackgroundImageResponse> {
  const res = await fetch(`${API_BASE}/conversions/${encodeURIComponent(jobId)}/pages/${pageIndex}/revert`, {
    method: 'POST',
  })
  if (!res.ok) throw new ApiError(res.status, await parseErrorMessage(res))
  return (await res.json()) as BackgroundImageResponse
}
