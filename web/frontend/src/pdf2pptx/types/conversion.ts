export type JobStatusValue = 'queued' | 'processing' | 'done' | 'failed'

export interface ConversionAcceptedResponse {
  jobId: string
  status: JobStatusValue
  statusUrl: string
}

export interface JobStatusResponse {
  jobId: string
  status: JobStatusValue
  progress?: string
  error?: string
  resultUrl?: string
}
