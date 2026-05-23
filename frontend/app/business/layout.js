export const metadata = {
  title: 'Jarvis for Business',
  description: 'AI-powered business tools by MG&CO Technologies',
}

export default function BusinessLayout({ children }) {
  return (
    <div style={{ minHeight: '100vh', background: '#0a0908', color: '#f3ead9' }}>
      <style>{`
        .biz-markdown h1, .biz-markdown h2 { color: #f3ead9; font-size: 1rem; font-weight: 700; margin: 14px 0 6px; }
        .biz-markdown h3 { color: #f3ead9; font-size: 0.9rem; font-weight: 600; margin: 10px 0 4px; }
        .biz-markdown p { margin: 0 0 8px; }
        .biz-markdown p:last-child { margin-bottom: 0; }
        .biz-markdown ul, .biz-markdown ol { margin: 6px 0 8px 18px; padding: 0; }
        .biz-markdown li { margin-bottom: 3px; }
        .biz-markdown strong { color: #f3ead9; font-weight: 600; }
        .biz-markdown code { background: rgba(243,234,217,0.08); border-radius: 3px; padding: 1px 5px; font-size: 12px; font-family: monospace; }
        .biz-markdown pre { background: rgba(243,234,217,0.05); border-radius: 6px; padding: 10px 14px; overflow-x: auto; margin: 8px 0; }
        .biz-markdown pre code { background: none; padding: 0; }
        .biz-markdown table { border-collapse: collapse; width: 100%; margin: 8px 0; }
        .biz-markdown th { background: rgba(200,75,49,0.12); color: #c84b31; font-weight: 600; padding: 6px 10px; border: 1px solid rgba(243,234,217,0.08); font-size: 12px; }
        .biz-markdown td { padding: 5px 10px; border: 1px solid rgba(243,234,217,0.07); font-size: 13px; }
        .biz-markdown blockquote { border-left: 2px solid rgba(200,75,49,0.4); margin: 8px 0; padding-left: 12px; color: rgba(243,234,217,0.6); }
      `}</style>
      {children}
    </div>
  )
}
