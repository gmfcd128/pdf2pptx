import { defineStore } from 'pinia'

export interface PageMeta {
  pageIndex: number
  sourceWidth: number
  sourceHeight: number
}

export interface Pdf2PptxState {
  // Which top-level screen App.vue renders: the upload/progress flow, or the
  // PPTist editor loaded with this job's converted slides.
  stage: 'upload' | 'editor'
  jobId: string | null
  // Keyed by Slide.id -- lets the manual-inpaint tool and the "revert to
  // original" action map the current slide back to its source job/page and
  // convert a canvas click into source-image pixel coordinates, without
  // polluting PPTist's own Slide type with pdf2pptx-specific fields.
  pages: Record<string, PageMeta>
}

export const usePdf2pptxStore = defineStore('pdf2pptx', {
  state: (): Pdf2PptxState => ({
    stage: 'upload',
    jobId: null,
    pages: {},
  }),

  actions: {
    startEditing(jobId: string, pages: Record<string, PageMeta>) {
      this.jobId = jobId
      this.pages = pages
      this.stage = 'editor'
    },

    reset() {
      this.jobId = null
      this.pages = {}
      this.stage = 'upload'
    },
  },
})
