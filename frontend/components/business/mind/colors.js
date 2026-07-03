// Cluster palette for The Mind (Batch 47). Maps mind_category -> node color.
export const MIND_COLORS = {
  revenue: '#cf8a5b',
  leads: '#41d99a',
  operations: '#ece6d9',
  people: '#c79bff',
  brand: '#ffb24a',
  tools: '#767066',
  risk: '#ff5d5d',
  general: '#9b948a',
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
export const QUEUE_BLUE = '#cf8a5b'

export function colorForCategory(cat) {
  return MIND_COLORS[cat] || MIND_COLORS.general
}
