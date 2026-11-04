<script setup lang="ts">
import { useSampleFiles } from "./sampleFiles";
const props = defineProps<{ sampleId: string }>();
const { files, error, download } = useSampleFiles(() => props.sampleId);
</script>
<template>
  <el-dropdown v-if="files.length" @command="download">
    <el-button plain>Download files</el-button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item v-for="file in files" :key="file.resource_id" :command="file.resource_id">{{
          file.name
        }}</el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
  <span v-if="error" role="alert">{{ error }}</span>
</template>
