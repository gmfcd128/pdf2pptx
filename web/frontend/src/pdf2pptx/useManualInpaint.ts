import { defineStore } from 'pinia'
import { useSlidesStore } from '@/store'
import { VIEWPORT_SIZE } from '@/configs/canvas'
import useHistorySnapshot from '@/hooks/useHistorySnapshot'
import { usePdf2pptxStore } from './store'
import { inpaintRegion, revertPage, type InpaintSource } from './api/slides'

// PPTist's viewport is always VIEWPORT_SIZE (1000) units wide; pdf2pptx loads
// its converted slides at a fixed 16:9 ratio (see UploadStage.vue), so the
// viewport height in the same units is always VIEWPORT_SIZE * this ratio.
const VIEWPORT_HEIGHT_RATIO = 0.5625

export interface ManualInpaintState {
  // Whether the "click 4 points" draw mode is active on the canvas.
  active: boolean
  // Collected points, in viewport units (0..1000 x, 0..562.5 y) -- the same
  // coordinate space as PPTElement left/top, not source-image pixels yet.
  points: [number, number][]
  source: InpaintSource
  submitting: boolean
  error: string | null
}

// A Pinia store rather than a plain composable: the draw-mode state must be
// shared between wherever it's triggered (Toolbar/SlideDesignPanel.vue) and
// where the clicks are actually captured (Canvas/index.vue's overlay) --
// a plain composable would give each call site its own independent state.
export const useManualInpaintStore = defineStore('manualInpaint', {
  state: (): ManualInpaintState => ({
    active: false,
    points: [],
    source: 'current',
    submitting: false,
    error: null,
  }),

  getters: {
    // The current slide's job/page metadata, if it came from a pdf2pptx
    // conversion (absent for a slide the user added by hand in the editor).
    currentPageMeta() {
      const slidesStore = useSlidesStore()
      const pdf2pptxStore = usePdf2pptxStore()
      const slide = slidesStore.currentSlide
      return slide ? pdf2pptxStore.pages[slide.id] ?? null : null
    },
  },

  actions: {
    setSource(source: InpaintSource) {
      this.source = source
    },

    start(source: InpaintSource) {
      this.active = true
      this.points = []
      this.source = source
      this.error = null
    },

    cancel() {
      this.active = false
      this.points = []
      this.submitting = false
    },

    addPoint(x: number, y: number) {
      if (!this.active || this.points.length >= 4) return
      this.points.push([x, y])
    },

    removeLastPoint() {
      this.points.pop()
    },

    async confirm() {
      const meta = this.currentPageMeta
      const jobId = usePdf2pptxStore().jobId
      if (!meta || !jobId || this.points.length !== 4) return

      this.submitting = true
      this.error = null
      try {
        const sourcePoints: [number, number][] = this.points.map(([x, y]) => [
          (x / VIEWPORT_SIZE) * meta.sourceWidth,
          (y / (VIEWPORT_SIZE * VIEWPORT_HEIGHT_RATIO)) * meta.sourceHeight,
        ])
        const result = await inpaintRegion(jobId, meta.pageIndex, sourcePoints, this.source)
        useSlidesStore().updateSlide({
          background: { type: 'image', image: result.backgroundImage, imageSize: 'stretch' },
        })
        useHistorySnapshot().addHistorySnapshot()
        this.cancel()
      }
      catch (err) {
        this.error = err instanceof Error ? err.message : '去背景文字失敗，請稍後再試。'
        this.submitting = false
      }
    },

    async revertToOriginal() {
      const meta = this.currentPageMeta
      const jobId = usePdf2pptxStore().jobId
      if (!meta || !jobId) return

      this.submitting = true
      this.error = null
      try {
        const result = await revertPage(jobId, meta.pageIndex)
        useSlidesStore().updateSlide({
          background: { type: 'image', image: result.backgroundImage, imageSize: 'stretch' },
        })
        useHistorySnapshot().addHistorySnapshot()
      }
      catch (err) {
        this.error = err instanceof Error ? err.message : '還原背景失敗，請稍後再試。'
      }
      finally {
        this.submitting = false
      }
    },
  },
})
