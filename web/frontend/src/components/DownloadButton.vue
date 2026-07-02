<script setup lang="ts">
import { resultDownloadUrl } from '../api/conversions'

const props = defineProps<{ jobId: string }>()
</script>

<template>
  <a :href="resultDownloadUrl(props.jobId)" download class="download-button"> 下載 PPTX 檔案 </a>
</template>

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
