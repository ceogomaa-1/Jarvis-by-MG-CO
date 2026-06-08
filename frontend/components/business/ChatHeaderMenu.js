'use client'
import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { BarChart3, BriefcaseBusiness, Menu, Plug, Settings, Star, User, UserCircle } from 'lucide-react'

import MorningQueueModal from './MorningQueueModal'
import BrandModal from './BrandModal'
import ConnectionsModal from './ConnectionsModal'
import MetricsModal from './MetricsModal'
import ProfileModal from './ProfileModal'

export default function ChatHeaderMenu({ userId, onBrandSaved }) {
  const [openModal, setOpenModal] = useState(null)
  const [panelOpen, setPanelOpen] = useState(false)

  const close = () => setOpenModal(null)
  const open = (key) => {
    setOpenModal(key)
    setPanelOpen(false)
  }

  const items = [
    { label: 'Morning Queue', icon: BriefcaseBusiness, onClick: () => open('queue') },
    { label: 'Adjust Numbers', icon: BarChart3, onClick: () => open('metrics') },
    { label: 'Connections', icon: Plug, onClick: () => open('connections') },
    { label: 'Brand Personalization', icon: Star, onClick: () => open('brand') },
    { label: 'My Profile', icon: User, onClick: () => open('profile') },
  ]

  return (
    <>
      <button
        className="os1-right-menu-button"
        onClick={() => setPanelOpen(v => !v)}
        aria-label="Open OS1 menu"
      >
        <Menu size={34} strokeWidth={2.8} />
      </button>

      <AnimatePresence>
        {panelOpen && (
          <motion.aside
            className="os1-right-panel"
            initial={{ x: 24, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 24, opacity: 0 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
          >
            <div className="os1-right-panel-head">
              <UserCircle size={26} />
              <button onClick={() => setPanelOpen(false)} aria-label="Close OS1 menu">
                <Menu size={31} strokeWidth={2.8} />
              </button>
            </div>

            <div className="os1-profile-copy">
              <h2>Mike Taylor</h2>
              <p>miketaylor@gmail.com</p>
              <p>User ID: xxxxxxxxx</p>
              <p>Joined May 13, 2026</p>
            </div>

            <div className="os1-right-divider" />

            <div className="os1-right-actions">
              {items.map(({ label, icon: Icon, onClick }) => (
                <button key={label} onClick={onClick}>
                  <Icon size={21} />
                  <span>{label}</span>
                </button>
              ))}
            </div>

            <div className="os1-right-footer">
              <span>Pro Tier</span>
              <Settings size={35} fill="currentColor" />
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

      <MorningQueueModal open={openModal === 'queue'}       onClose={close} userId={userId} />
      <BrandModal        open={openModal === 'brand'}       onClose={close} userId={userId} onSaved={onBrandSaved} />
      <ConnectionsModal  open={openModal === 'connections'} onClose={close} userId={userId} />
      <MetricsModal      open={openModal === 'metrics'}     onClose={close} userId={userId} />
      <ProfileModal      open={openModal === 'profile'}     onClose={close} />
    </>
  )
}
