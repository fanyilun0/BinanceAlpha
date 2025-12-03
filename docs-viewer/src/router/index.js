import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import ChartView from '../views/ChartView.vue'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: Home
  },
  {
    path: '/chart',
    name: 'Chart',
    component: ChartView
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router

