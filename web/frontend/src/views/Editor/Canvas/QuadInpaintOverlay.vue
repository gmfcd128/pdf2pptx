<template>
  <div
    class="quad-inpaint-overlay"
    ref="overlayRef"
    :style="{ width: VIEWPORT_SIZE + 'px', height: viewportHeight + 'px' }"
    @mousedown.stop="handleClick"
    @contextmenu.stop.prevent="manualInpaint.removeLastPoint()"
  >
    <svg class="quad-svg" :width="VIEWPORT_SIZE" :height="viewportHeight" overflow="visible">
      <polyline
        v-if="points.length > 1"
        :points="polylinePoints"
        fill="none"
        stroke="#d14424"
        stroke-width="2"
      />
      <line
        v-if="points.length === 4"
        :x1="points[3][0]" :y1="points[3][1]"
        :x2="points[0][0]" :y2="points[0][1]"
        stroke="#d14424" stroke-width="2" stroke-dasharray="4 3"
      />
      <circle v-for="(p, index) in points" :key="index" :cx="p[0]" :cy="p[1]" r="5" fill="#d14424" />
    </svg>
  </div>
</template>

<script lang="ts">
import { computed, defineComponent, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useMainStore, useSlidesStore } from '@/store'
import { VIEWPORT_SIZE } from '@/configs/canvas'
import { useManualInpaintStore } from '@/pdf2pptx/useManualInpaint'

// The click-capture + point/line markers for pdf2pptx's manual-inpaint tool
// (see useManualInpaint.ts). Lives inside .viewport (the div Canvas/index.vue
// applies `transform: scale(canvasScale)` to) so that, like every ordinary
// slide element, its points are authored directly in viewport units (0..1000,
// 0..VIEWPORT_SIZE*viewportRatio) and the surrounding CSS transform handles
// the on-screen scaling for free -- only the reverse direction (a raw mouse
// click back into those same units) needs explicit math, mirroring
// Canvas/hooks/useInsertFromCreateSelection.ts's formatCreateSelection.
export default defineComponent({
  name: 'quad-inpaint-overlay',
  setup() {
    const manualInpaint = useManualInpaintStore()
    const { canvasScale } = storeToRefs(useMainStore())
    const { viewportRatio } = storeToRefs(useSlidesStore())

    const overlayRef = ref<HTMLElement>()
    const points = computed(() => manualInpaint.points)
    const viewportHeight = computed(() => VIEWPORT_SIZE * viewportRatio.value)
    const polylinePoints = computed(() => points.value.map(p => p.join(',')).join(' '))

    const handleClick = (e: MouseEvent) => {
      if (points.value.length >= 4 || !overlayRef.value) return
      const rect = overlayRef.value.getBoundingClientRect()
      const x = (e.clientX - rect.left) / canvasScale.value
      const y = (e.clientY - rect.top) / canvasScale.value
      manualInpaint.addPoint(x, y)
    }

    return {
      manualInpaint,
      overlayRef,
      points,
      viewportHeight,
      polylinePoints,
      handleClick,
      VIEWPORT_SIZE,
    }
  },
})
</script>

<style lang="scss" scoped>
.quad-inpaint-overlay {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 10;
  cursor: crosshair;
}
.quad-svg {
  position: absolute;
  top: 0;
  left: 0;
  overflow: visible;
  pointer-events: none;
}
</style>
