'use client';
import dynamic from 'next/dynamic';

const AgentationToolbar = dynamic(
  () => import('agentation').then(mod => ({ default: mod.Agentation })),
  { ssr: false }
);

export default function AgentationProvider() {
  if (process.env.NODE_ENV !== 'development') return null;
  return <AgentationToolbar endpoint="http://localhost:4747" />;
}
