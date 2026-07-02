<script setup lang="ts">
import { computed } from 'vue'
import FileUpload from './components/FileUpload.vue'
import ConversionProgress from './components/ConversionProgress.vue'
import DownloadButton from './components/DownloadButton.vue'
import { useConversionJob } from './composables/useConversionJob'

const { jobId, status, progress, error, submit, reset } = useConversionJob()

const isActive = computed(() => status.value !== null)
const isFinished = computed(() => status.value === 'done' || status.value === 'failed')

function onSelect(file: File) {
  void submit(file)
}
</script>

<template>
  <div class="page">
    <header class="header">
      <h1>PDF 轉 PPTX 轉換工具</h1>
      <p class="subtitle">上傳影像化的 PDF，自動辨識文字並轉換為可編輯的 PowerPoint 簡報</p>
    </header>

    <main class="card">
      <FileUpload v-if="!isActive" @select="onSelect" />

      <div v-else class="job-panel">
        <ConversionProgress :status="status" :progress="progress" :error="error" />
        <div v-if="isFinished" class="actions">
          <DownloadButton v-if="status === 'done' && jobId" :job-id="jobId" />
          <button class="reset-button" @click="reset">轉換另一份檔案</button>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 3rem 1.5rem;
}

.header {
  text-align: center;
  margin-bottom: 2rem;
}

.header h1 {
  font-size: 1.75rem;
  margin: 0 0 0.5rem;
  color: #111827;
}

.subtitle {
  color: #6b7280;
  margin: 0;
}

.card {
  width: 100%;
  max-width: 560px;
  background: white;
  border-radius: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  padding: 1.5rem;
}

.job-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  margin-top: 0.5rem;
}

.reset-button {
  background: none;
  border: none;
  color: #3b82f6;
  font-size: 0.95rem;
  cursor: pointer;
  padding: 0.25rem;
}

.reset-button:hover {
  text-decoration: underline;
}
</style>
