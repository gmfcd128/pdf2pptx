import { onUnmounted, ref } from 'vue'
import { ApiError, getJobStatus, submitConversion } from '../api/conversions'
import type { JobStatusValue } from '../types/conversion'

const POLL_INTERVAL_MS = 2000

export function useConversionJob() {
  const jobId = ref<string | null>(null)
  const status = ref<JobStatusValue | null>(null)
  const progress = ref<string | null>(null)
  const error = ref<string | null>(null)
  const submitting = ref(false)

  let pollHandle: ReturnType<typeof setInterval> | null = null

  function stopPolling() {
    if (pollHandle !== null) {
      clearInterval(pollHandle)
      pollHandle = null
    }
  }

  async function poll() {
    if (!jobId.value) return
    try {
      const job = await getJobStatus(jobId.value)
      status.value = job.status
      progress.value = job.progress ?? null
      error.value = job.error ?? null
      if (job.status === 'done' || job.status === 'failed') {
        stopPolling()
      }
    } catch (err) {
      stopPolling()
      error.value = err instanceof ApiError ? err.message : '無法取得轉換進度，請稍後再試。'
      status.value = 'failed'
    }
  }

  async function submit(file: File) {
    reset()
    submitting.value = true
    try {
      const accepted = await submitConversion(file)
      jobId.value = accepted.jobId
      status.value = accepted.status
      pollHandle = setInterval(poll, POLL_INTERVAL_MS)
    } catch (err) {
      error.value = err instanceof ApiError ? err.message : '上傳失敗，請稍後再試。'
      status.value = 'failed'
    } finally {
      submitting.value = false
    }
  }

  function reset() {
    stopPolling()
    jobId.value = null
    status.value = null
    progress.value = null
    error.value = null
  }

  onUnmounted(stopPolling)

  return { jobId, status, progress, error, submitting, submit, reset }
}
