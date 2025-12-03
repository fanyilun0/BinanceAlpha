<script setup>
</script>

<template>
  <router-view />
</template>

<style>
:root {
  --bg-color: #ffffff;
  --text-color: #24292e;
  --sidebar-bg: #f5f5f5;
  --border-color: #ddd;
  --hover-color: #e0e0e0;
  --active-color: #e0e0e0;
}

.dark-mode {
  --bg-color: #1a1a1a;
  --text-color: #e0e0e0;
  --sidebar-bg: #2d2d2d;
  --border-color: #404040;
  --hover-color: #404040;
  --active-color: #505050;
}

body {
  margin: 0;
  padding: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
}
</style>
