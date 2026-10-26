import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ChatComposer from './ChatComposer.vue'

describe('ChatComposer', () => {
  it('emits the submitted question', async () => {
    const wrapper = mount(ChatComposer, {
      props: { modelValue: '', disabled: false },
      global: {
        stubs: {
          'el-input': { template: '<div><input @input="$emit(\'update:modelValue\', $event.target.value)" @keyup.enter="$emit(\'submit\')" /></div>' },
          'el-button': { template: '<button @click="$emit(\'click\')"><slot /></button>' },
        },
      },
    })

    await wrapper.get('input').setValue('合同是否有效')
    await wrapper.get('input').trigger('keyup.enter')

    expect(wrapper.emitted('update:modelValue')).toEqual([['合同是否有效']])
    expect(wrapper.emitted('submit')).toBeTruthy()
  })
})
