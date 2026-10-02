const CIVIL_CODE_SECTIONS = [
  { id: 'civil-general', label: '总则编', count: 204, startArticle: 1, endArticle: 204 },
  { id: 'civil-property', label: '物权编', count: 258, startArticle: 205, endArticle: 462 },
  { id: 'civil-contract', label: '合同编', count: 526, startArticle: 463, endArticle: 988 },
  { id: 'civil-personality', label: '人格权编', count: 51, startArticle: 989, endArticle: 1039 },
  { id: 'civil-family', label: '婚姻家庭编', count: 79, startArticle: 1040, endArticle: 1118 },
  { id: 'civil-inheritance', label: '继承编', count: 44, startArticle: 1119, endArticle: 1162 },
  { id: 'civil-tort', label: '侵权责任编', count: 98, startArticle: 1163, endArticle: 1260 },
]

const QUESTION_PRESETS = {
  'civil-code': [
    '合同成立需要满足哪些条件？',
    '格式条款什么情况下无效？',
    '定金和订金有什么区别？',
    '什么情况下可以解除合同？',
    '违约责任如何计算赔偿金额？',
    '借款合同没有约定利息怎么办？',
  ],
  'criminal-law': ['正当防卫的成立条件是什么？', '犯罪未遂和犯罪中止有什么区别？', '自首和立功如何影响量刑？'],
  'labor-law': ['劳动者加班工资应如何计算？', '用人单位在哪些情形下不得解除劳动合同？', '试用期的期限和工资有哪些规定？'],
  'labor-contract-law': ['违法解除劳动合同的赔偿如何计算？', '无固定期限劳动合同在什么情况下应当订立？', '竞业限制补偿金应如何支付？'],
  'company-law': ['有限责任公司股东的出资义务有哪些？', '股东会和董事会的职权如何区分？', '公司法定代表人的责任有哪些？'],
  'patent-law': ['专利权的保护期限是多久？', '哪些情形不授予专利权？', '专利侵权的赔偿如何确定？'],
  'trademark-law': ['注册商标的有效期是多久？', '哪些标志不能作为商标注册？', '商标侵权如何认定？'],
  'copyright-law': ['著作权保护哪些作品？', '著作权的保护期限是多久？', '合理使用作品有哪些情形？'],
}

export function buildStatuteTree(knowledgeBases) {
  return knowledgeBases
    .filter((item) => item.type === 'statute' && item.status === 'READY')
    .map((item) => {
      const base = {
        id: `law:${item.slug}`,
        label: item.name,
        slug: item.slug,
        lawName: item.name,
        count: item.document_count,
      }
      if (item.slug !== 'civil-code') return base
      return {
        ...base,
        children: CIVIL_CODE_SECTIONS.map((section) => ({
          ...section,
          knowledgeBaseSlug: item.slug,
          lawName: item.name,
        })),
      }
    })
}

export function getQuestionPresets(knowledgeBaseSlug) {
  return QUESTION_PRESETS[knowledgeBaseSlug] || [
    '这部法律主要调整哪些事项？',
    '与这部法律相关的常见权利义务有哪些？',
    '发生争议时应当注意哪些法律问题？',
  ]
}
