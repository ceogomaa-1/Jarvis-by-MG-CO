export default function manifest() {
  return {
    name: 'Rue — Your Personal AI',
    short_name: 'Rue',
    description: 'The first AI that actually gets to know you. Built by MG&CO Technologies.',
    start_url: '/',
    display: 'standalone',
    background_color: '#0a0908',
    theme_color: '#0a0908',
    icons: [
      { src: '/favicon.png', sizes: '512x512', type: 'image/png' },
      { src: '/apple-icon.png', sizes: '180x180', type: 'image/png' },
    ],
  }
}
