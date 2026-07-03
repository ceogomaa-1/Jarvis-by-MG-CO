// Cluster palette for The Mind (Batch 47). Maps mind_category -> node color.
export const MIND_COLORS = {
  revenue: '#ff2e51',
  leads: '#41d99a',
  operations: '#f4f4f2',
  people: '#c79bff',
  brand: '#ffb24a',
  tools: '#71717a',
  risk: '#ff5d5d',
  general: '#a1a1aa',
}

export const MIND_LABELS = {
  revenue: 'Revenue',
  leads: 'Leads & Customers',
  operations: 'Operations',
  people: 'People',
  brand: 'Brand & Marketing',
  tools: 'Tools & Connections',
  risk: 'Risk',
  general: 'General',
}

export const GOLD = '#ffd24a'
export const QUEUE_BLUE = '#ff2e51'

export function colorForCategory(cat) {
  return MIND_COLORS[cat] || MIND_COLORS.general
}
