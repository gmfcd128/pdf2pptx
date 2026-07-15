<template>
  <div class="page">
    <header class="header">
      <h1>PDF 轉 PPTX 轉換工具</h1>
      <p class="subtitle">上傳影像化的 PDF，自動辨識文字並轉換為可編輯的簡報</p>
    </header>

    <main class="card">
      <FileUpload v-if="!isActive" @select="onSelect" />

      <div v-else class="job-panel">
        <ConversionProgress :status="status" :progress="progress" :error="error" :loading-editor="loadingEditor" />
        <div v-if="status === 'failed' || loadError" class="actions">
          <p v-if="loadError" class="upload-error">{{ loadError }}</p>
          <button class="reset-button" @click="reset">轉換另一份檔案</button>
        </div>
      </div>
    </main>
  </div>
</template>

<script lang="ts">
import { computed, defineComponent, ref, watch } from 'vue'
import { useSlidesStore } from '@/store'
import type { PPTElement, Slide } from '@/types/slides'
import { useConversionJob } from './composables/useConversionJob'
import { getSlides } from './api/slides'
import { usePdf2pptxStore, type PageMeta } from './store'
import FileUpload from './components/FileUpload.vue'
import ConversionProgress from './components/ConversionProgress.vue'

export default defineComponent({
  name: 'upload-stage',
  components: {
    FileUpload,
    ConversionProgress,
  },
  setup() {
    const { jobId, status, progress, error, submit, reset: resetJob } = useConversionJob()
    const slidesStore = useSlidesStore()
    const pdf2pptxStore = usePdf2pptxStore()

    const isActive = computed(() => status.value !== null)

    const loadingEditor = ref(false)
    const loadError = ref<string | null>(null)

    const onSelect = (file: File) => {
      void submit(file)
    }

    const reset = () => {
      resetJob()
      loadError.value = null
    }

    const openEditor = async () => {
      if (!jobId.value) return

      loadingEditor.value = true
      loadError.value = null
      try {
        const { viewportRatio, canvasWidthIn, slides } = await getSlides(jobId.value)

        const pages: Record<string, PageMeta> = {}
        const editorSlides: Slide[] = slides.map(s => {
          pages[s.id] = {
            pageIndex: s.pageIndex,
            sourceWidth: s.sourceWidth,
            sourceHeight: s.sourceHeight,
          }
          return {
            id: s.id,
            elements: s.elements as unknown as PPTElement[],
            background: {
              type: 'image',
              image: s.backgroundImage,
              imageSize: 'stretch',
            },
          }
        })

        slidesStore.setSlides(editorSlides)
        slidesStore.setViewportRatio(viewportRatio)
        slidesStore.setViewportWidthIn(canvasWidthIn)
        slidesStore.updateSlideIndex(0)
        pdf2pptxStore.startEditing(jobId.value, pages)
      }
      catch (err) {
        loadError.value = err instanceof Error ? err.message : '載入編輯器失敗，請稍後再試。'
      }
      finally {
        loadingEditor.value = false
      }
    }

    // Auto-advance straight into the editor as soon as conversion finishes --
    // no manual "開始編輯" click in between. Watching status (rather than
    // calling openEditor directly from the poll callback) keeps this the
    // single place that reacts to a job reaching 'done', regardless of what
    // triggers that transition.
    watch(status, value => {
      if (value === 'done') void openEditor()
    })

    return {
      status,
      progress,
      error,
      isActive,
      loadingEditor,
      loadError,
      onSelect,
      reset,
    }
  },
})
</script>

<style scoped>
.page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 3rem 1.5rem;
  background-color: #f3f4f6;
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

.upload-error {
  color: #dc2626;
  margin: 0;
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
