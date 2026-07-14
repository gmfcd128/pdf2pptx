<template>
  <div v-if="status" class="progress-panel">
    <div v-if="status !== 'failed'" class="status-row">
      <span v-if="status === 'queued' || status === 'processing' || loadingEditor" class="spinner"></span>
      <span class="status-label">{{ loadingEditor ? '正在載入編輯器…' : statusLabel }}</span>
      <span v-if="progressLabel && !loadingEditor" class="progress-text">{{ progressLabel }}</span>
    </div>
    <div v-else class="error-row">
      <span class="status-label error">{{ statusLabel }}</span>
      <p class="error-message">{{ error ?? '發生未知錯誤，請重新嘗試。' }}</p>
    </div>
  </div>
</template>

<script lang="ts">
import { computed, defineComponent, PropType } from 'vue'
import type { JobStatusValue } from '../types/conversion'

export default defineComponent({
  name: 'conversion-progress',
  props: {
    status: {
      type: String as PropType<JobStatusValue | null>,
      default: null,
    },
    progress: {
      type: String as PropType<string | null>,
      default: null,
    },
    error: {
      type: String as PropType<string | null>,
      default: null,
    },
    loadingEditor: {
      type: Boolean,
      default: false,
    },
  },
  setup(props) {
    const statusLabel = computed(() => {
      switch (props.status) {
        case 'queued':
          return '排隊中…'
        case 'processing':
          return '轉換中…'
        case 'done':
          return '轉換完成'
        case 'failed':
          return '轉換失敗'
        default:
          return ''
      }
    })

    // Python reports progress as "3/23" (page 3 of 23 pages processed).
    const progressLabel = computed(() => {
      if (!props.progress) return null
      const [current, total] = props.progress.split('/')
      if (!current || !total) return null
      return `第 ${current} / ${total} 頁`
    })

    return {
      statusLabel,
      progressLabel,
    }
  },
})
</script>

<style scoped>
.progress-panel {
  padding: 2rem 1.5rem;
  text-align: center;
}

.status-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.6rem;
}

.status-label {
  font-size: 1.1rem;
  font-weight: 600;
  color: #1f2937;
}

.status-label.error {
  color: #dc2626;
}

.progress-text {
  color: #6b7280;
}

.error-row {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
}

.error-message {
  color: #6b7280;
  margin: 0;
}

.spinner {
  width: 1.1rem;
  height: 1.1rem;
  border: 2px solid #d1d5db;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
