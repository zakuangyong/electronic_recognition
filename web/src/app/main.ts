import { createApp, h } from 'vue'
import { createPinia } from 'pinia'
import { RouterView } from 'vue-router'

import { createAppRouter } from './router'
import './styles/tokens.css'
import './styles/base.css'
import './styles/styles.css'

const app = createApp({
  name: 'ElectronicRecognitionApp',
  render: () => h(RouterView),
})

app.use(createPinia())
app.use(createAppRouter())
app.mount('#app')
