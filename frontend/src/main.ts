import { createApp } from 'vue'
import { createPinia } from 'pinia'
import {
  ElAlert, ElAside, ElAvatar, ElButton, ElCard, ElCheckbox, ElCol, ElCollapse,
  ElCollapseItem, ElContainer, ElDatePicker, ElDescriptions, ElDescriptionsItem,
  ElDialog, ElDivider, ElDrawer, ElDropdown, ElDropdownItem, ElDropdownMenu,
  ElEmpty, ElForm, ElFormItem, ElIcon, ElInput, ElInputNumber, ElLink, ElLoading,
  ElMain, ElMenu, ElMenuItem, ElOption, ElProgress, ElRadioButton, ElRadioGroup,
  ElRow, ElSelect, ElSkeleton, ElSpace, ElTabPane, ElTable, ElTableColumn, ElTabs,
  ElTag, ElTimeline, ElTimelineItem, ElTree, ElUpload,
} from 'element-plus'
import 'element-plus/dist/index.css'
import {
  ArrowRight, ChatDotRound, Checked, Collection, Connection, DataAnalysis, Document,
  DocumentChecked, Files, Loading, Reading, Search, Setting, Star, SwitchButton, UserFilled,
} from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'
import './styles/index.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)
;[
  ElAlert, ElAside, ElAvatar, ElButton, ElCard, ElCheckbox, ElCol, ElCollapse,
  ElCollapseItem, ElContainer, ElDatePicker, ElDescriptions, ElDescriptionsItem,
  ElDialog, ElDivider, ElDrawer, ElDropdown, ElDropdownItem, ElDropdownMenu,
  ElEmpty, ElForm, ElFormItem, ElIcon, ElInput, ElInputNumber, ElLink, ElLoading,
  ElMain, ElMenu, ElMenuItem, ElOption, ElProgress, ElRadioButton, ElRadioGroup,
  ElRow, ElSelect, ElSkeleton, ElSpace, ElTabPane, ElTable, ElTableColumn, ElTabs,
  ElTag, ElTimeline, ElTimelineItem, ElTree, ElUpload,
].forEach((component) => app.use(component))

;[
  ArrowRight, ChatDotRound, Checked, Collection, Connection, DataAnalysis, Document,
  DocumentChecked, Files, Loading, Reading, Search, Setting, Star, SwitchButton, UserFilled,
].forEach((component) => {
  if (component.name) {
    app.component(component.name, component)
  }
})

app.mount('#app')
