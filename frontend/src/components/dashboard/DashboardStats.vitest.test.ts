import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import DashboardStats from './DashboardStats.vue'

describe('DashboardStats', () => {
  it('renders the four supplied research metrics', () => {
    const wrapper = mount(DashboardStats, {
      props: {
        stats: {
          lawCount: '1260',
          caseCount: '24',
          verifyRate: '100',
          queryCount: '8',
        },
      },
      global: {
        stubs: {
          'el-row': { template: '<div><slot /></div>' },
          'el-col': { template: '<div><slot /></div>' },
        },
      },
    })

    expect(wrapper.text()).toContain('收录法条')
    expect(wrapper.text()).toContain('1260')
    expect(wrapper.text()).toContain('法条校验率')
    expect(wrapper.text()).toContain('100%')
  })
})
