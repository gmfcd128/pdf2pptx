<script setup lang="ts">
import { ref } from 'vue'

const emit = defineEmits<{ select: [file: File] }>()

const isDragging = ref(false)
const rejectionMessage = ref<string | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)

function isPdf(file: File): boolean {
  return file.name.toLowerCase().endsWith('.pdf')
}

function handleFile(file: File) {
  rejectionMessage.value = null
  if (!isPdf(file)) {
    rejectionMessage.value = '僅接受 PDF 檔案，請重新選擇。'
    return
  }
  emit('select', file)
}

function onDrop(e: DragEvent) {
  isDragging.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) handleFile(file)
}

function onFileInputChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) handleFile(file)
  input.value = ''
}

function openFileDialog() {
  fileInput.value?.click()
}
</script>

<template>
  <div
    class="upload-zone"
    :class="{ dragging: isDragging }"
    @dragover.prevent="isDragging = true"
    @dragleave.prevent="isDragging = false"
    @drop.prevent="onDrop"
    @click="openFileDialog"
  >
    <input
      ref="fileInput"
      type="file"
      accept=".pdf,application/pdf"
      class="hidden-input"
      @change="onFileInputChange"
    />
    <p class="upload-title">拖曳 PDF 檔案至此，或點擊選擇檔案</p>
    <p class="upload-hint">僅支援 PDF 格式，轉換過程約需 1～3 分鐘</p>
    <p v-if="rejectionMessage" class="upload-error">{{ rejectionMessage }}</p>
  </div>
</template>

<style scoped>
.upload-zone {
  border: 2px dashed #9aa5b1;
  border-radius: 12px;
  padding: 3.5rem 1.5rem;
  text-align: center;
  cursor: pointer;
  transition:
    border-color 0.15s,
    background-color 0.15s;
}

.upload-zone.dragging {
  border-color: #3b82f6;
  background-color: #eff6ff;
}

.upload-title {
  font-size: 1.1rem;
  font-weight: 600;
  margin: 0 0 0.5rem;
  color: #1f2937;
}

.upload-hint {
  color: #6b7280;
  margin: 0;
  font-size: 0.9rem;
}

.upload-error {
  color: #dc2626;
  margin-top: 0.75rem;
  font-weight: 500;
}

.hidden-input {
  display: none;
}
</style>
