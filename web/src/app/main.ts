import { createApp, h, KeepAlive, type VNode } from 'vue'
import { createPinia } from 'pinia'
import { RouterView } from 'vue-router'

import { createAppRouter } from './router'
import './styles/tokens.css'
import './styles/base.css'
import './styles/styles.css'

type RouterViewSlotProps = {
  Component?: VNode
}

const app = createApp({
  name: 'ElectronicRecognitionApp',
  render: () =>
    h(RouterView, null, {
      default: ({ Component }: RouterViewSlotProps) =>
        Component
          ? h(
              KeepAlive,
              { include: ['WorkbenchView', 'DrawingCorrectionView'] },
              () => Component,
            )
          : null,
    }),
})

app.use(createPinia())
app.use(createAppRouter())
app.mount('#app')
