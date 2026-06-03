export const AGENTS = [
  {
    id: 'operator-strategist',
    group: 'operator',
    name: 'Strategist',
    role: 'Plans overnight cycles — picks high-leverage moves aligned with your North Star.',
    icon: 'Brain',
    status: 'idle',
  },
  {
    id: 'operator-researcher',
    group: 'operator',
    name: 'Researcher',
    role: 'Runs live web research to back each strategic move with facts and competitive context.',
    icon: 'Search',
    status: 'idle',
  },
  {
    id: 'operator-creator',
    group: 'operator',
    name: 'Creator',
    role: 'Drafts deliverables in parallel — emails, campaigns, docs — for each approved move.',
    icon: 'Sparkles',
    status: 'idle',
  },
  {
    id: 'operator-packager',
    group: 'operator',
    name: 'Packager',
    role: 'Packages creator outputs into morning-queue action cards ready for your approval.',
    icon: 'Package',
    status: 'idle',
  },
  {
    id: 'creation-strategist',
    group: 'creation',
    name: 'Strategist',
    role: 'Breaks your real-time creation request into a structured brief for all sub-agents.',
    icon: 'Compass',
    status: 'idle',
  },
  {
    id: 'creation-copywriter',
    group: 'creation',
    name: 'Copywriter',
    role: 'Writes persuasive copy — headlines, body, CTAs — calibrated to your audience.',
    icon: 'PenTool',
    status: 'idle',
  },
  {
    id: 'creation-designer',
    group: 'creation',
    name: 'Designer',
    role: 'Produces layout guidance, color systems, and visual direction for each deliverable.',
    icon: 'Palette',
    status: 'idle',
  },
  {
    id: 'creation-researcher',
    group: 'creation',
    name: 'Researcher',
    role: 'Finds market data, competitor angles, and audience insights to ground the creation.',
    icon: 'Telescope',
    status: 'idle',
  },
  {
    id: 'creation-analyst',
    group: 'creation',
    name: 'Analyst',
    role: 'Models expected impact — conversion lift, reach, ROI — before the artifact ships.',
    icon: 'BarChart3',
    status: 'idle',
  },
  {
    id: 'creation-reporter',
    group: 'creation',
    name: 'Reporter',
    role: 'Assembles the final artifact and a one-page executive summary for your review.',
    icon: 'FileText',
    status: 'idle',
  },
]

export function getOrbitPosition(index, total, radius) {
  const angle = (2 * Math.PI * index) / total - Math.PI / 2
  return {
    x: radius * Math.cos(angle),
    y: radius * Math.sin(angle),
  }
}
