'use client'
import { useState } from 'react'
import { CircleMenu } from '@/components/ui/circle-menu'
import { ClipboardList, Palette, Plug, BarChart3, User } from 'lucide-react'

import MorningQueueModal from './MorningQueueModal'
import BrandModal from './BrandModal'
import ConnectionsModal from './ConnectionsModal'
import MetricsModal from './MetricsModal'
import ProfileModal from './ProfileModal'

export default function ChatHeaderMenu({ userId, onBrandSaved }) {
  const [openModal, setOpenModal] = useState(null)

  const close = () => setOpenModal(null)
  const open = (key) => setOpenModal(key)

  // 90° arc from straight down (π/2) to straight left (π) — fans into the page, never clips the viewport
  const arcStart = Math.PI / 2
  const arcSpan = Math.PI / 2

  const items = [
    { label: 'Morning Queue',  icon: <ClipboardList size={18} />, onClick: () => open('queue') },
    { label: 'Brand',          icon: <Palette size={18} />,       onClick: () => open('brand') },
    { label: 'Connections',    icon: <Plug size={18} />,          onClick: () => open('connections') },
    { label: 'Update Numbers', icon: <BarChart3 size={18} />,     onClick: () => open('metrics') },
    { label: 'My Profile',     icon: <User size={18} />,          onClick: () => open('profile') },
  ]

  return (
    <>
      <div style={{ position: 'fixed', top: 68, right: 20, zIndex: 50 }}>
        <CircleMenu items={items} arcStart={arcStart} arcSpan={arcSpan} />
      </div>

      <MorningQueueModal open={openModal === 'queue'}       onClose={close} userId={userId} />
      <BrandModal        open={openModal === 'brand'}       onClose={close} userId={userId} onSaved={onBrandSaved} />
      <ConnectionsModal  open={openModal === 'connections'} onClose={close} userId={userId} />
      <MetricsModal      open={openModal === 'metrics'}     onClose={close} userId={userId} />
      <ProfileModal      open={openModal === 'profile'}     onClose={close} />
    </>
  )
}
