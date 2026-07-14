import { defineStore } from 'pinia'
import { useSlidesStore } from '@/store'
import { VIEWPORT_SIZE } from '@/configs/canvas'
import useHistorySnapshot from '@/hooks/useHistorySnapshot'
import { usePdf2pptxStore } from './store'
import { inpaintRegion, restoreRegion } from './api/slides'

// PPTist's viewport is always VIEWPORT_SIZE (1000) units wide; pdf2pptx loads
// its converted slides at a fixed 16:9 ratio (see UploadStage.vue), so the
// viewport height in the same units is always VIEWPORT_SIZE * this ratio.
const VIEWPORT_HEIGHT_RATIO = 0.5625

// Which of the two background-repair actions the current area-select session
// is for -- both share the same "click 4 points" draw step, only what
// confirm() does with the selected region differs.
export type ManualInpaintMode = 'restore' | 'inpaint'

export interface ManualInpaintState {
  // Whether the "click 4 points" draw mode is active on the canvas.
  active: boolean
  mode: ManualInpaintMode | null
  // Collected points, in viewport units (0..1000 x, 0..562.5 y) -- the same
  // coordinate space as PPTElement left/top, not source-image pixels yet.
  points: [number, number][]
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
    mode: null,
    points: [],
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
    start(mode: ManualInpaintMode) {
      this.active = true
      this.mode = mode
      this.points = []
      this.error = null
    },

    cancel() {
      this.active = false
      this.mode = null
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
      if (!meta || !jobId || !this.mode || this.points.length !== 4) return

      this.submitting = true
      this.error = null
      try {
        const sourcePoints: [number, number][] = this.points.map(([x, y]) => [
          (x / VIEWPORT_SIZE) * meta.sourceWidth,
          (y / (VIEWPORT_SIZE * VIEWPORT_HEIGHT_RATIO)) * meta.sourceHeight,
        ])
        const result = this.mode === 'restore'
          ? await restoreRegion(jobId, meta.pageIndex, sourcePoints)
          : await inpaintRegion(jobId, meta.pageIndex, sourcePoints)

        useSlidesStore().updateSlide({
          background: { type: 'image', image: result.backgroundImage, imageSize: 'stretch' },
        })
        useHistorySnapshot().addHistorySnapshot()
        this.cancel()
      }
      catch (err) {
        this.error = err instanceof Error
          ? err.message
          : this.mode === 'restore' ? '還原區域失敗，請稍後再試。' : '去背景文字失敗，請稍後再試。'
        this.submitting = false
      }
    },
  },
})
