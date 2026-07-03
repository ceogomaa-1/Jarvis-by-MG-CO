'use client'

import { AnimatePresence, motion } from 'framer-motion'
import React, { useState } from 'react'
import { Menu, X } from 'lucide-react'
import { cn } from '@/lib/utils'

const CONSTANTS = {
  itemSize: 48,
  containerSize: 48,
  arcRadius: 130,
  openStagger: 0.02,
  closeStagger: 0.07,
}

const pointOnCircle = (
  i: number,
  n: number,
  r: number,
  arcStart: number,
  arcSpan: number
) => {
  const isFullCircle = Math.abs(arcSpan - 2 * Math.PI) < 0.01
  let theta: number
  if (isFullCircle) {
    theta = arcStart + (arcSpan * i) / n
  } else if (n === 1) {
    theta = arcStart + arcSpan / 2
  } else {
    theta = arcStart + (arcSpan * i) / (n - 1)
  }
  return { x: r * Math.cos(theta), y: r * Math.sin(theta) }
}

interface CircleMenuItem {
  label: string
  icon: React.ReactNode
  href?: string
  onClick?: () => void
}

interface MenuItemProps {
  item: CircleMenuItem
  index: number
  totalItems: number
  isOpen: boolean
  arcStart: number
  arcSpan: number
  itemBgClass: string
}

const MenuItem = ({ item, index, totalItems, isOpen, arcStart, arcSpan, itemBgClass }: MenuItemProps) => {
  const { x, y } = pointOnCircle(index, totalItems, CONSTANTS.arcRadius, arcStart, arcSpan)
  const [hovering, setHovering] = useState(false)

  const handleClick = (e: React.MouseEvent) => {
    if (item.onClick) {
      e.preventDefault()
      item.onClick()
    }
  }

  const buttonContent = (
    <motion.div
      animate={{
        x: isOpen ? x : 0,
        y: isOpen ? y : 0,
        opacity: isOpen ? 1 : 0,
      }}
      whileHover={{ scale: 1.1, transition: { duration: 0.1 } }}
      transition={{
        delay: isOpen ? index * CONSTANTS.openStagger : index * CONSTANTS.closeStagger,
        type: 'spring',
        stiffness: 300,
        damping: 30,
      }}
      style={{
        height: CONSTANTS.itemSize - 2,
        width: CONSTANTS.itemSize - 2,
        position: 'absolute',
        top: 1,
        left: 1,
      }}
      className={cn(
        'rounded-full flex items-center justify-center cursor-pointer transition-colors',
        itemBgClass
      )}
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
    >
      <div className="text-[#f3ead9]">{item.icon}</div>
      <AnimatePresence>
        {hovering && isOpen && (
          <motion.span
            initial={{ opacity: 0, y: -2 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -2 }}
            transition={{ duration: 0.15 }}
            className="font-arcade text-[9px] tracking-wider text-[#f3ead9] absolute top-full left-1/2 -translate-x-1/2 mt-1.5 whitespace-nowrap bg-[#0a0a0a]/90 border border-[rgba(243,234,217,0.15)] px-2 py-0.5 rounded uppercase pointer-events-none"
            style={{ backdropFilter: 'blur(8px)' }}
          >
            {item.label}
          </motion.span>
        )}
      </AnimatePresence>
    </motion.div>
  )

  if (item.onClick) {
    return (
      <button onClick={handleClick} className="absolute top-0 left-0" style={{ width: 0, height: 0 }} aria-label={item.label}>
        {buttonContent}
      </button>
    )
  }

  return (
    <a href={item.href || '#'} className="absolute top-0 left-0" style={{ width: 0, height: 0 }} aria-label={item.label}>
      {buttonContent}
    </a>
  )
}

interface MenuTriggerProps {
  isOpen: boolean
  setIsOpen: (v: boolean) => void
  openIcon: React.ReactNode
  closeIcon: React.ReactNode
  triggerColor: string
}

const MenuTrigger = ({ isOpen, setIsOpen, openIcon, closeIcon, triggerColor }: MenuTriggerProps) => (
  <motion.button
    style={{ height: CONSTANTS.itemSize, width: CONSTANTS.itemSize, backgroundColor: triggerColor }}
    className="rounded-full flex items-center justify-center cursor-pointer outline-none ring-0 hover:brightness-110 transition-all duration-150 z-50 relative shadow-[0_8px_24px_rgba(200,75,49,0.4)]"
    onClick={() => setIsOpen(!isOpen)}
    whileTap={{ scale: 0.92 }}
  >
    <AnimatePresence mode="popLayout">
      {isOpen ? (
        <motion.span
          key="menu-close"
          initial={{ opacity: 0, filter: 'blur(10px)', rotate: -90 }}
          animate={{ opacity: 1, filter: 'blur(0px)', rotate: 0 }}
          exit={{ opacity: 0, filter: 'blur(10px)', rotate: 90 }}
          transition={{ duration: 0.2 }}
        >
          {closeIcon}
        </motion.span>
      ) : (
        <motion.span
          key="menu-open"
          initial={{ opacity: 0, filter: 'blur(10px)', rotate: 90 }}
          animate={{ opacity: 1, filter: 'blur(0px)', rotate: 0 }}
          exit={{ opacity: 0, filter: 'blur(10px)', rotate: -90 }}
          transition={{ duration: 0.2 }}
        >
          {openIcon}
        </motion.span>
      )}
    </AnimatePresence>
  </motion.button>
)

interface CircleMenuProps {
  items: CircleMenuItem[]
  openIcon?: React.ReactNode
  closeIcon?: React.ReactNode
  arcStart?: number
  arcSpan?: number
  triggerColor?: string
  itemBgClass?: string
}

export const CircleMenu = ({
  items,
  openIcon = <Menu size={20} className="text-white" />,
  closeIcon = <X size={20} className="text-white" />,
  arcStart = -Math.PI / 2,
  arcSpan = 2 * Math.PI,
  triggerColor = '#c84b31',
  itemBgClass = 'bg-[#171411] border border-[rgba(243,234,217,0.18)] hover:bg-[#2a2a2a]',
}: CircleMenuProps) => {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <div
      className="relative"
      style={{ width: CONSTANTS.containerSize, height: CONSTANTS.containerSize }}
    >
      <MenuTrigger
        isOpen={isOpen}
        setIsOpen={setIsOpen}
        openIcon={openIcon}
        closeIcon={closeIcon}
        triggerColor={triggerColor}
      />
      <div className="absolute top-0 left-0 z-0" style={{ width: 0, height: 0 }}>
        {items.map((item, index) => (
          <MenuItem
            key={`circle-menu-item-${index}`}
            item={item}
            index={index}
            totalItems={items.length}
            isOpen={isOpen}
            arcStart={arcStart}
            arcSpan={arcSpan}
            itemBgClass={itemBgClass}
          />
        ))}
      </div>
    </div>
  )
}

export default CircleMenu
