import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ProviderSelector from './ProviderSelector.vue'

describe('ProviderSelector', () => {
  it('emits the selected provider key', async () => {
    const wrapper = mount(ProviderSelector, {
      props: {
        modelValue: 'deepseek',
        providers: [
          { key: 'deepseek', label: 'DeepSeek', models: ['deepseek-chat'] },
          { key: 'openai', label: 'OpenAI', models: ['gpt-4.1'] },
        ],
      },
    })

    await wrapper.get('[data-provider="openai"]').trigger('click')

    expect(wrapper.emitted('update:modelValue')).toEqual([['openai']])
  })
})
