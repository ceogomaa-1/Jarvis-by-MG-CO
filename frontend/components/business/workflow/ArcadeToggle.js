'use client';
import { usePathname, useRouter } from 'next/navigation';
import { motion } from 'framer-motion';

export default function ArcadeToggle() {
  const pathname = usePathname();
  const router = useRouter();
  const isWorkflow = pathname?.includes('/workflow');

  function toggle() {
    router.push(isWorkflow ? '/business/chat' : '/business/workflow');
  }

  return (
    <div className="fixed top-3 left-1/2 -translate-x-1/2 z-[45] flex items-center gap-3">
      <span className={`font-arcade text-[7px] tracking-wider uppercase transition-colors duration-300 ${
        !isWorkflow ? 'text-[#c84b31]' : 'text-[rgba(243,234,217,0.25)]'
      }`}>
        Chat
      </span>

      <button
        onClick={toggle}
        className="relative w-16 h-8 rounded-full border border-[rgba(243,234,217,0.15)] bg-[rgba(10,10,10,0.8)] backdrop-blur-md cursor-pointer transition-all duration-300 hover:border-[rgba(243,234,217,0.25)]"
        aria-label={isWorkflow ? 'Switch to Chat' : 'Switch to Workflow'}
      >
        <div className="absolute inset-[3px] rounded-full bg-[rgba(243,234,217,0.04)]" />
        <motion.div
          className="absolute top-[3px] w-[26px] h-[26px] rounded-full bg-[#c84b31] shadow-[0_0_12px_rgba(200,75,49,0.4)] flex items-center justify-center"
          animate={{ left: isWorkflow ? 'calc(100% - 29px)' : '3px' }}
          transition={{ type: 'spring', stiffness: 500, damping: 30 }}
        >
          <div className="relative w-2 h-2 opacity-40">
            <div className="absolute w-[6px] h-[1px] bg-[#0a0a0a] top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
            <div className="absolute w-[1px] h-[6px] bg-[#0a0a0a] top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
          </div>
        </motion.div>
      </button>

      <span className={`font-arcade text-[7px] tracking-wider uppercase transition-colors duration-300 ${
        isWorkflow ? 'text-[#c84b31]' : 'text-[rgba(243,234,217,0.25)]'
      }`}>
        Canvas
      </span>
    </div>
  );
}
