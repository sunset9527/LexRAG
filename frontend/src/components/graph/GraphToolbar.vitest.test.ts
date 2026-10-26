import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import GraphToolbar from './GraphToolbar.vue'

describe('GraphToolbar', () => {
  it('emits the selected law and a reload request', async () => {
    const wrapper = mount(GraphToolbar, {
      props: { modelValue: '', laws: ['民法典'] },
      global: {
        stubs: {
          'el-select': {
            props: ['modelValue'],
            template: '<select @change="$emit(\'update:modelValue\', $event.target.value)"><option value="民法典">民法典</option></select>',
          },
          'el-option': true,
          'el-button': { template: '<button @click="$emit(\'click\')"><slot /></button>' },
        },
      },
    })

    await wrapper.get('select').setValue('民法典')
    await wrapper.get('button').trigger('click')

    expect(wrapper.emitted('update:modelValue')).toEqual([['民法典']])
    expect(wrapper.emitted('load')).toBeTruthy()
  })
})
