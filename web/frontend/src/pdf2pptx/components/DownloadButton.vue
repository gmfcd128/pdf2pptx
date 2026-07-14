<template>
  <a :href="resultDownloadUrl(jobId)" download class="download-button"> 下載 PPTX 檔案 </a>
</template>

<script lang="ts">
import { defineComponent, PropType } from 'vue'
import { resultDownloadUrl } from '../api/conversions'

export default defineComponent({
  name: 'download-button',
  props: {
    jobId: {
      type: String as PropType<string>,
      required: true,
    },
  },
  setup() {
    return {
      resultDownloadUrl,
    }
  },
})
</script>

<style scoped>
.download-button {
  display: inline-block;
  padding: 0.65rem 1.75rem;
  background-color: #16a34a;
  color: white;
  border-radius: 8px;
  text-decoration: none;
  font-weight: 600;
  transition: background-color 0.15s;
}

.download-button:hover {
  background-color: #15803d;
}
</style>
