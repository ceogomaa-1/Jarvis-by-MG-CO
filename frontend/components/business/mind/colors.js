// Cluster palette for The Mind (Batch 47). Maps mind_category -> node color.
export const MIND_COLORS = {
  revenue: '#2d7ff9',
  leads: '#41d99a',
  operations: '#e8e8e8',
  people: '#c79bff',
  brand: '#ffb24a',
  tools: '#6e6e6e',
  risk: '#ff5d5d',
  general: '#9a9a9a',
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
export const QUEUE_BLUE = '#2d7ff9'

export function colorForCategory(cat) {
  return MIND_COLORS[cat] || MIND_COLORS.general
}
