export interface KnowledgeBasePresentation {
  slug: string
  name: string
  type: string
  status: string
  document_count: number
}

export interface LawTreeNode {
  id: string
  label: string
  slug?: string
  knowledgeBaseSlug?: string
  lawName: string
  count: number
  startArticle?: number
  endArticle?: number
  children?: LawTreeNode[]
}

export function buildStatuteTree(knowledgeBases: KnowledgeBasePresentation[]): LawTreeNode[]
export function getQuestionPresets(knowledgeBaseSlug: string): string[]
