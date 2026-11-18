import {
  BookOpen,
  GitBranch,
  Monitor,
  Shield,
  TrendingUp,
  Wrench,
  Zap,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import faqContent from './faqContent.json'

/**
 * FAQ content model. Answers are composed from typed blocks so the renderer
 * stays generic — no per-question JSX special cases. Inline `code` spans are
 * written with backticks and parsed by the renderer.
 */
export type FAQBlock =
  | { type: 'p'; text: string }
  | { type: 'list'; items: string[] }
  | { type: 'steps'; items: string[] }
  | { type: 'note'; text: string }
  | { type: 'links'; links: { label: string; href: string }[] }

export interface FAQItem {
  id: string
  question: string
  blocks: FAQBlock[]
}

export interface FAQCategory {
  id: string
  title: string
  icon: LucideIcon
  items: FAQItem[]
}

/** Plain text of an item, used by the search filter. */
export function faqItemSearchText(item: FAQItem): string {
  const parts: string[] = [item.question]
  for (const block of item.blocks) {
    if (block.type === 'p' || block.type === 'note') parts.push(block.text)
    else if (block.type === 'list' || block.type === 'steps')
      parts.push(block.items.join(' '))
    else if (block.type === 'links')
      parts.push(block.links.map((l) => l.label).join(' '))
  }
  return parts.join(' ').toLowerCase()
}

const iconMap: Record<string, LucideIcon> = {
  BookOpen,
  GitBranch,
  Monitor,
  Shield,
  TrendingUp,
  Wrench,
  Zap,
}

/**
 * FAQ categories loaded from faqContent.json. The JSON file holds all text
 * content; this module maps iconKey strings to actual Lucide icons.
 * Future edits: modify faqContent.json — no code change needed.
 */
export const faqCategories: FAQCategory[] = faqContent.categories.map(
  (category) => ({
    id: category.id,
    title: category.title,
    icon: iconMap[category.iconKey] ?? BookOpen,
    items: category.items.map((item) => ({
      id: item.id,
      question: item.question,
      blocks: item.blocks as FAQBlock[],
    })),
  })
)
