'use client'

import * as React from 'react'
import * as TooltipPrimitive from '@radix-ui/react-tooltip'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { ArrowUp, Paperclip, Square, X, StopCircle, Mic, Image as ImageIcon, SquareTerminal, PenLine } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { useRouter } from 'next/navigation'
import { cn } from '@/lib/utils'

// ────────────────────────────────────────────────────────────────
// SSR-safe one-time style injection
// ────────────────────────────────────────────────────────────────
let _stylesInjected = false
function injectScrollbarStyles() {
  if (_stylesInjected || typeof document === 'undefined') return
  _stylesInjected = true
  const styles = `
    .jarvis-prompt-textarea::-webkit-scrollbar { width: 6px; }
    .jarvis-prompt-textarea::-webkit-scrollbar-track { background: transparent; }
    .jarvis-prompt-textarea::-webkit-scrollbar-thumb { background-color: #3a3a3a; border-radius: 3px; }
    .jarvis-prompt-textarea::-webkit-scrollbar-thumb:hover { background-color: #4a4a4a; }
  `
  const sheet = document.createElement('style')
  sheet.innerText = styles
  document.head.appendChild(sheet)
}

// ────────────────────────────────────────────────────────────────
// Textarea
// ────────────────────────────────────────────────────────────────
interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  className?: string
}
const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, ...props }, ref) => (
    <textarea
      className={cn(
        'jarvis-prompt-textarea font-pixel flex w-full rounded-md border-none bg-transparent px-3 py-2.5 text-[15px] text-[#e8e8e8] placeholder:text-[#6e6e6e] placeholder:font-pixel placeholder:text-[14px] focus-visible:outline-none focus-visible:ring-0 disabled:cursor-not-allowed disabled:opacity-50 min-h-[44px] resize-none',
        className
      )}
      ref={ref}
      rows={1}
      {...props}
    />
  )
)
Textarea.displayName = 'Textarea'

// ────────────────────────────────────────────────────────────────
// Tooltip
// ────────────────────────────────────────────────────────────────
const TooltipProvider = TooltipPrimitive.Provider
const Tooltip = TooltipPrimitive.Root
const TooltipTrigger = TooltipPrimitive.Trigger
const TooltipContent = React.forwardRef<
  React.ElementRef<typeof TooltipPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>
>(({ className, sideOffset = 4, ...props }, ref) => (
  <TooltipPrimitive.Content
    ref={ref}
    sideOffset={sideOffset}
    className={cn(
      'z-50 overflow-hidden rounded-md border border-[rgba(232,232,232,0.12)] bg-[#1a1a1a] px-3 py-1.5 text-sm text-[#e8e8e8] shadow-md animate-in fade-in-0 zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95',
      className
    )}
    {...props}
  />
))
TooltipContent.displayName = TooltipPrimitive.Content.displayName

// ────────────────────────────────────────────────────────────────
// Dialog (for image preview)
// ────────────────────────────────────────────────────────────────
const Dialog = DialogPrimitive.Root
const DialogPortal = DialogPrimitive.Portal
const DialogOverlay = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cn(
      'fixed inset-0 z-50 bg-black/70 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
      className
    )}
    {...props}
  />
))
DialogOverlay.displayName = DialogPrimitive.Overlay.displayName

const DialogContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ className, children, ...props }, ref) => (
  <DialogPortal>
    <DialogOverlay />
    <DialogPrimitive.Content
      ref={ref}
      className={cn(
        'fixed left-[50%] top-[50%] z-50 grid w-full max-w-[90vw] md:max-w-[800px] translate-x-[-50%] translate-y-[-50%] gap-4 border border-[rgba(232,232,232,0.12)] bg-[#0a0a0a] p-0 shadow-xl duration-300 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 rounded-2xl',
        className
      )}
      {...props}
    >
      {children}
      <DialogPrimitive.Close className="absolute right-4 top-4 z-10 rounded-full bg-[rgba(232,232,232,0.08)] p-2 hover:bg-[rgba(232,232,232,0.16)] transition-all">
        <X className="h-5 w-5 text-[#e8e8e8]" />
        <span className="sr-only">Close</span>
      </DialogPrimitive.Close>
    </DialogPrimitive.Content>
  </DialogPortal>
))
DialogContent.displayName = DialogPrimitive.Content.displayName

const DialogTitle = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    className={cn('text-lg font-semibold leading-none tracking-tight text-[#e8e8e8]', className)}
    {...props}
  />
))
DialogTitle.displayName = DialogPrimitive.Title.displayName

// ────────────────────────────────────────────────────────────────
// Button
// ────────────────────────────────────────────────────────────────
interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'outline' | 'ghost'
  size?: 'default' | 'sm' | 'lg' | 'icon'
}
const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'default', size = 'default', ...props }, ref) => {
    const variantClasses: Record<string, string> = {
      default: 'bg-[#e8e8e8] hover:bg-[#e8e8e8]/85 text-[#0a0a0a]',
      outline: 'border border-[rgba(232,232,232,0.12)] bg-transparent hover:bg-[rgba(232,232,232,0.06)]',
      ghost: 'bg-transparent hover:bg-[rgba(232,232,232,0.06)]',
    }
    const sizeClasses: Record<string, string> = {
      default: 'h-10 px-4 py-2',
      sm: 'h-8 px-3 text-sm',
      lg: 'h-12 px-6',
      icon: 'h-8 w-8 rounded-full aspect-square',
    }
    return (
      <button
        className={cn(
          'inline-flex items-center justify-center font-medium transition-colors focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50',
          variantClasses[variant],
          sizeClasses[size],
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = 'Button'

// ────────────────────────────────────────────────────────────────
// VoiceRecorder
// ────────────────────────────────────────────────────────────────
interface VoiceRecorderProps {
  isRecording: boolean
  onStartRecording: () => void
  onStopRecording: (duration: number) => void
  visualizerBars?: number
}
const VoiceRecorder: React.FC<VoiceRecorderProps> = ({
  isRecording,
  onStartRecording,
  onStopRecording,
  visualizerBars = 32,
}) => {
  const [time, setTime] = React.useState(0)
  const timerRef = React.useRef<ReturnType<typeof setInterval> | null>(null)

  React.useEffect(() => {
    if (isRecording) {
      onStartRecording()
      timerRef.current = setInterval(() => setTime(t => t + 1), 1000)
    } else {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
      onStopRecording(time)
      setTime(0)
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isRecording])

  const fmt = (s: number) =>
    `${Math.floor(s / 60).toString().padStart(2, '0')}:${(s % 60).toString().padStart(2, '0')}`

  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center w-full transition-all duration-300 py-3',
        isRecording ? 'opacity-100' : 'opacity-0 h-0'
      )}
    >
      <div className="flex items-center gap-2 mb-3">
        <div className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
        <span className="font-mono text-sm text-[#e8e8e8]/80">{fmt(time)}</span>
      </div>
      <div className="w-full h-10 flex items-center justify-center gap-0.5 px-4">
        {[...Array(visualizerBars)].map((_, i) => (
          <div
            key={i}
            className="w-0.5 rounded-full bg-[#e8e8e8]/50 animate-pulse"
            style={{
              height: `${Math.max(15, Math.random() * 100)}%`,
              animationDelay: `${i * 0.05}s`,
              animationDuration: `${0.5 + Math.random() * 0.5}s`,
            }}
          />
        ))}
      </div>
    </div>
  )
}

// ────────────────────────────────────────────────────────────────
// Image preview dialog
// ────────────────────────────────────────────────────────────────
const ImageViewDialog: React.FC<{ imageUrl: string | null; onClose: () => void }> = ({
  imageUrl,
  onClose,
}) => {
  if (!imageUrl) return null
  return (
    <Dialog open={!!imageUrl} onOpenChange={onClose}>
      <DialogContent className="p-0 border-none bg-transparent shadow-none max-w-[90vw] md:max-w-[800px]">
        <DialogTitle className="sr-only">Image Preview</DialogTitle>
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.95 }}
          transition={{ duration: 0.2 }}
          className="relative bg-[#0a0a0a] rounded-2xl overflow-hidden shadow-2xl"
        >
          <img src={imageUrl} alt="Preview" className="w-full max-h-[80vh] object-contain rounded-2xl" />
        </motion.div>
      </DialogContent>
    </Dialog>
  )
}

// ────────────────────────────────────────────────────────────────
// PromptInput Context
// ────────────────────────────────────────────────────────────────
interface PromptInputContextType {
  isLoading: boolean
  value: string
  setValue: (value: string) => void
  maxHeight: number | string
  onSubmit?: () => void
  disabled?: boolean
}
const PromptInputContext = React.createContext<PromptInputContextType>({
  isLoading: false,
  value: '',
  setValue: () => {},
  maxHeight: 240,
  onSubmit: undefined,
  disabled: false,
})
function usePromptInput() {
  return React.useContext(PromptInputContext)
}

interface PromptInputProps {
  isLoading?: boolean
  value?: string
  onValueChange?: (value: string) => void
  maxHeight?: number | string
  onSubmit?: () => void
  children: React.ReactNode
  className?: string
  disabled?: boolean
  onDragOver?: (e: React.DragEvent) => void
  onDragLeave?: (e: React.DragEvent) => void
  onDrop?: (e: React.DragEvent) => void
}
const PromptInput = React.forwardRef<HTMLDivElement, PromptInputProps>(
  (
    {
      className,
      isLoading = false,
      maxHeight = 240,
      value,
      onValueChange,
      onSubmit,
      children,
      disabled = false,
      onDragOver,
      onDragLeave,
      onDrop,
    },
    ref
  ) => {
    const [internalValue, setInternalValue] = React.useState(value || '')
    const handleChange = (newValue: string) => {
      setInternalValue(newValue)
      onValueChange?.(newValue)
    }
    return (
      <TooltipProvider>
        <PromptInputContext.Provider
          value={{
            isLoading,
            value: value ?? internalValue,
            setValue: onValueChange ?? handleChange,
            maxHeight,
            onSubmit,
            disabled,
          }}
        >
          <div
            ref={ref}
            className={cn(
              'rounded-[22px] border border-[#3d3d3d] bg-[#131313] p-3 transition-all duration-300',
              isLoading && 'border-[#555555]',
              className
            )}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
          >
            {children}
          </div>
        </PromptInputContext.Provider>
      </TooltipProvider>
    )
  }
)
PromptInput.displayName = 'PromptInput'

// ────────────────────────────────────────────────────────────────
// PromptInputTextarea
// ────────────────────────────────────────────────────────────────
interface PromptInputTextareaProps {
  disableAutosize?: boolean
  placeholder?: string
}
const PromptInputTextarea: React.FC<
  PromptInputTextareaProps & React.ComponentProps<typeof Textarea>
> = ({ className, onKeyDown, disableAutosize = false, placeholder, ...props }) => {
  const { value, setValue, maxHeight, onSubmit, disabled } = usePromptInput()
  const textareaRef = React.useRef<HTMLTextAreaElement>(null)

  React.useEffect(() => {
    if (disableAutosize || !textareaRef.current) return
    textareaRef.current.style.height = 'auto'
    textareaRef.current.style.height =
      typeof maxHeight === 'number'
        ? `${Math.min(textareaRef.current.scrollHeight, maxHeight)}px`
        : `min(${textareaRef.current.scrollHeight}px, ${maxHeight})`
  }, [value, maxHeight, disableAutosize])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSubmit?.()
    }
    onKeyDown?.(e as React.KeyboardEvent<HTMLTextAreaElement>)
  }

  return (
    <Textarea
      ref={textareaRef}
      value={value}
      onChange={e => setValue(e.target.value)}
      onKeyDown={handleKeyDown}
      className={cn('text-base', className)}
      disabled={disabled}
      placeholder={placeholder}
      {...props}
    />
  )
}

// ────────────────────────────────────────────────────────────────
// PromptInputActions / Action
// ────────────────────────────────────────────────────────────────
const PromptInputActions: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({
  children,
  className,
  ...props
}) => (
  <div className={cn('flex items-center gap-2', className)} {...props}>
    {children}
  </div>
)

interface PromptInputActionProps extends React.ComponentProps<typeof Tooltip> {
  tooltip: React.ReactNode
  children: React.ReactNode
  side?: 'top' | 'bottom' | 'left' | 'right'
  className?: string
}
const PromptInputAction: React.FC<PromptInputActionProps> = ({
  tooltip,
  children,
  className,
  side = 'top',
  ...props
}) => {
  const { disabled } = usePromptInput()
  return (
    <Tooltip {...props}>
      <TooltipTrigger asChild disabled={disabled}>
        {children}
      </TooltipTrigger>
      <TooltipContent side={side} className={className as string | undefined}>
        {tooltip}
      </TooltipContent>
    </Tooltip>
  )
}

// ────────────────────────────────────────────────────────────────
// Divider between toggle pills
// ────────────────────────────────────────────────────────────────
const CustomDivider: React.FC = () => (
  <div className="relative h-6 w-[1.5px] mx-1">
    <div className="absolute inset-0 bg-gradient-to-t from-transparent via-[#2d7ff9]/50 to-transparent rounded-full" />
  </div>
)

// ────────────────────────────────────────────────────────────────
// Main PromptInputBox — public component
// ────────────────────────────────────────────────────────────────
export interface PromptInputBoxProps {
  onSend?: (message: string, files?: File[]) => void
  isLoading?: boolean
  placeholder?: string
  className?: string
  enableVoice?: boolean
  enableUpload?: boolean
  showViewToggle?: boolean
  showGoToggle?: boolean
  goMode?: boolean
  onGoModeChange?: (next: boolean) => void
}

export const PromptInputBox = React.forwardRef<HTMLDivElement, PromptInputBoxProps>((props, ref) => {
  const {
    onSend = () => {},
    isLoading = false,
    placeholder = 'Ask Jarvis...',
    className,
    enableVoice = false,
    enableUpload = true,
    showViewToggle = false,
    showGoToggle = false,
    goMode = false,
    onGoModeChange = () => {},
  } = props

  const MAX_FILES = 5
  const router = useRouter()

  const [input, setInput] = React.useState('')
  const [fileEntries, setFileEntries] = React.useState<Array<{id: string; file: File; preview: string}>>([])
  const [selectedImage, setSelectedImage] = React.useState<string | null>(null)
  const [isRecording, setIsRecording] = React.useState(false)
  const [showSearch, setShowSearch] = React.useState(false)
  const [showOperator, setShowOperator] = React.useState(false)
  const [showShowMe, setShowShowMe] = React.useState(false)
  const uploadInputRef = React.useRef<HTMLInputElement>(null)
  const imageInputRef = React.useRef<HTMLInputElement>(null)
  const promptBoxRef = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    injectScrollbarStyles()
  }, [])

  const handleToggleChange = (which: 'search' | 'operator' | 'showme') => {
    if (which === 'search') {
      setShowSearch(p => !p); setShowOperator(false); setShowShowMe(false)
    } else if (which === 'operator') {
      setShowOperator(p => !p); setShowSearch(false); setShowShowMe(false)
    } else {
      setShowShowMe(p => !p); setShowSearch(false); setShowOperator(false)
    }
  }

  const isImageFile = (file: File) => file.type.startsWith('image/')
  const isSupportedFile = (file: File) =>
    file.type.startsWith('image/') ||
    file.type === 'application/pdf' ||
    file.type === 'text/plain' ||
    file.type === 'text/csv' ||
    file.name.endsWith('.csv') ||
    file.name.endsWith('.txt') ||
    file.name.endsWith('.md')

  const addFiles = React.useCallback((newFiles: File[]) => {
    setFileEntries(prev => {
      const available = MAX_FILES - prev.length
      if (available <= 0) return prev
      const toAdd = newFiles.filter(f => isSupportedFile(f) && f.size <= 20 * 1024 * 1024).slice(0, available)
      const nextEntries = [...prev]
      toAdd.forEach(file => {
        const id = Math.random().toString(36).slice(2)
        if (isImageFile(file)) {
          nextEntries.push({ id, file, preview: '' })
          const reader = new FileReader()
          reader.onload = (e) => {
            const preview = e.target?.result as string
            setFileEntries(cur => cur.map(entry => entry.id === id ? { ...entry, preview } : entry))
          }
          reader.readAsDataURL(file)
        } else {
          nextEntries.push({ id, file, preview: 'file:' + file.name })
        }
      })
      return nextEntries
    })
  }, [])

  const removeFileEntry = (id: string) => {
    setFileEntries(prev => prev.filter(e => e.id !== id))
  }

  const handleDragOver = React.useCallback((e: React.DragEvent) => { e.preventDefault(); e.stopPropagation() }, [])
  const handleDragLeave = React.useCallback((e: React.DragEvent) => { e.preventDefault(); e.stopPropagation() }, [])
  const handleDrop = React.useCallback((e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation()
    const dropped = Array.from(e.dataTransfer.files)
    if (dropped.length > 0) addFiles(dropped)
  }, [addFiles])

  const handlePaste = React.useCallback((e: ClipboardEvent) => {
    const items = e.clipboardData?.items
    if (!items) return
    const pastedFiles: File[] = []
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.indexOf('image') !== -1) {
        const file = items[i].getAsFile()
        if (file) pastedFiles.push(file)
      }
    }
    if (pastedFiles.length > 0) { e.preventDefault(); addFiles(pastedFiles) }
  }, [addFiles])

  React.useEffect(() => {
    document.addEventListener('paste', handlePaste)
    return () => document.removeEventListener('paste', handlePaste)
  }, [handlePaste])

  const handleSubmit = () => {
    if (!input.trim() && fileEntries.length === 0) return
    let prefix = ''
    if (showSearch) prefix = '[Search: '
    else if (showOperator) prefix = '[Operator: '
    else if (showShowMe) prefix = '[ShowMe: '
    const formatted = prefix ? `${prefix}${input}]` : input
    onSend(formatted, fileEntries.map(e => e.file))
    setInput('')
    setFileEntries([])
  }

  const hasContent = input.trim() !== '' || fileEntries.length > 0

  return (
    <>
      <PromptInput
        value={input}
        onValueChange={setInput}
        isLoading={isLoading}
        onSubmit={handleSubmit}
        className={cn(isRecording && 'border-red-500/70', className)}
        disabled={isLoading || isRecording}
        ref={ref || promptBoxRef}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {fileEntries.length > 0 && !isRecording && (
          <div className="flex flex-wrap gap-2 p-0 pb-1">
            {fileEntries.map((entry) => (
              <div key={entry.id} className="relative group w-16 h-16 rounded-xl overflow-hidden flex-shrink-0"
                style={{ backgroundColor: 'rgba(232,232,232,0.06)', border: '1px solid rgba(232,232,232,0.1)' }}>
                {isImageFile(entry.file) && entry.preview ? (
                  <div className="w-full h-full cursor-pointer" onClick={() => setSelectedImage(entry.preview)}>
                    <img src={entry.preview} alt={entry.file.name} className="h-full w-full object-cover" />
                  </div>
                ) : isImageFile(entry.file) && !entry.preview ? (
                  <div className="w-full h-full flex items-center justify-center">
                    <span className="text-xs" style={{ color: 'rgba(232,232,232,0.3)' }}>…</span>
                  </div>
                ) : (
                  <div className="w-full h-full flex flex-col items-center justify-center p-1 gap-0.5">
                    <span className="text-sm">{entry.file.type === 'application/pdf' ? '📄' : '📝'}</span>
                    <span className="text-center w-full truncate px-0.5"
                      style={{ fontFamily: 'system-ui', fontSize: '6px', color: 'rgba(232,232,232,0.5)' }}>
                      {entry.file.name}
                    </span>
                  </div>
                )}
                <button
                  type="button"
                  onClick={e => { e.stopPropagation(); removeFileEntry(entry.id) }}
                  className="absolute top-0.5 right-0.5 w-4 h-4 flex items-center justify-center rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                  style={{ backgroundColor: 'rgba(0,0,0,0.75)' }}
                >
                  <X className="h-2.5 w-2.5 text-white" />
                </button>
              </div>
            ))}
            {fileEntries.length < MAX_FILES && (
              <button
                type="button"
                onClick={() => uploadInputRef.current?.click()}
                className="w-16 h-16 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{
                  backgroundColor: 'rgba(232,232,232,0.02)',
                  border: '1px dashed rgba(232,232,232,0.12)',
                  color: 'rgba(232,232,232,0.25)',
                  fontSize: '20px', cursor: 'pointer',
                }}
              >
                +
              </button>
            )}
          </div>
        )}

        <div className={cn('transition-all duration-300', isRecording ? 'h-0 overflow-hidden opacity-0' : 'opacity-100')}>
          <PromptInputTextarea
            placeholder={
              showSearch ? 'Search the web…'
              : showOperator ? 'Tell Jarvis what to build for you…'
              : showShowMe ? 'Ask Jarvis to walk you through…'
              : placeholder
            }
            className="text-base"
          />
        </div>

        {isRecording && (
          <VoiceRecorder
            isRecording={isRecording}
            onStartRecording={() => {}}
            onStopRecording={(duration) => {
              setIsRecording(false)
              onSend(`[Voice message - ${duration}s]`, [])
            }}
          />
        )}

        <PromptInputActions className="flex items-center justify-between gap-2 p-0 pt-2">
          {/* Left: icon cluster — image, attach, operator (terminal), show-me (pen) */}
          <div className={cn('flex items-center gap-1 transition-opacity duration-300', isRecording ? 'opacity-0 invisible h-0' : 'opacity-100 visible')}>
            {enableUpload && (
              <>
                <PromptInputAction tooltip="Add an image">
                  <button
                    type="button"
                    onClick={() => imageInputRef.current?.click()}
                    className="flex h-8 w-8 text-[#9a9a9a] cursor-pointer items-center justify-center rounded-lg transition-colors hover:text-[#e8e8e8] hover:bg-[rgba(255,255,255,0.05)]"
                    disabled={isRecording}
                  >
                    <ImageIcon className="h-[18px] w-[18px]" />
                    <input
                      ref={imageInputRef}
                      type="file"
                      multiple
                      className="hidden"
                      onChange={e => {
                        if (e.target.files && e.target.files.length > 0)
                          addFiles(Array.from(e.target.files))
                        if (e.target) e.target.value = ''
                      }}
                      accept="image/*"
                    />
                  </button>
                </PromptInputAction>

                <PromptInputAction tooltip="Attach files">
                  <button
                    type="button"
                    onClick={() => uploadInputRef.current?.click()}
                    className="flex h-8 w-8 text-[#9a9a9a] cursor-pointer items-center justify-center rounded-lg transition-colors hover:text-[#e8e8e8] hover:bg-[rgba(255,255,255,0.05)]"
                    disabled={isRecording}
                  >
                    <Paperclip className="h-[17px] w-[17px]" />
                    <input
                      ref={uploadInputRef}
                      type="file"
                      multiple
                      className="hidden"
                      onChange={e => {
                        if (e.target.files && e.target.files.length > 0)
                          addFiles(Array.from(e.target.files))
                        if (e.target) e.target.value = ''
                      }}
                      accept="image/*,application/pdf,.pdf,.txt,.csv,.md"
                    />
                  </button>
                </PromptInputAction>
              </>
            )}

            {/* Operator mode — terminal icon */}
            <PromptInputAction tooltip="Operator — Jarvis builds it for you">
              <button
                type="button"
                onClick={() => handleToggleChange('operator')}
                className={cn(
                  'flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg transition-colors',
                  showOperator
                    ? 'text-[#2d7ff9] bg-[rgba(45,127,249,0.12)]'
                    : 'text-[#9a9a9a] hover:text-[#e8e8e8] hover:bg-[rgba(255,255,255,0.05)]'
                )}
              >
                <SquareTerminal className="h-[18px] w-[18px]" />
              </button>
            </PromptInputAction>

            {/* Show Me mode — pen icon */}
            <PromptInputAction tooltip="Show Me How — guided walkthrough">
              <button
                type="button"
                onClick={() => handleToggleChange('showme')}
                className={cn(
                  'flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg transition-colors',
                  showShowMe
                    ? 'text-[#2d7ff9] bg-[rgba(45,127,249,0.12)]'
                    : 'text-[#9a9a9a] hover:text-[#e8e8e8] hover:bg-[rgba(255,255,255,0.05)]'
                )}
              >
                <PenLine className="h-[17px] w-[17px]" />
              </button>
            </PromptInputAction>
          </div>

          {/* Center: Chat View | Canvas View pill */}
          {showViewToggle && !isRecording && (
            <div className="flex items-center rounded-full bg-[#2e2e2e] p-[3px]">
              <button
                type="button"
                className="font-pixel rounded-full bg-[#4a4a4a] px-3.5 py-[3px] text-[12px] text-[#e8e8e8]"
              >
                Chat View
              </button>
              <span className="mx-1.5 h-4 w-px bg-[#4a4a4a]" />
              <button
                type="button"
                onClick={() => router.push('/business/workflow')}
                className="font-pixel rounded-full px-3.5 py-[3px] text-[12px] text-[#9a9a9a] transition-colors hover:text-[#e8e8e8]"
              >
                Canvas View
              </button>
            </div>
          )}

          {/* Jarvis | Jarvis GO pill — opt-in mode that skips intent pre-routing and
              sends every message straight to the brain (tool-driven, no classifier). */}
          {showGoToggle && !isRecording && (
            <div
              className="flex items-center rounded-full bg-[#2e2e2e] p-[3px]"
              title={goMode ? 'Jarvis GO — everything goes straight to the brain' : 'Classic Jarvis — fast-routes obvious requests'}
            >
              <button
                type="button"
                onClick={() => onGoModeChange(false)}
                className={cn(
                  'font-pixel rounded-full px-3.5 py-[3px] text-[12px] transition-colors',
                  !goMode ? 'bg-[#4a4a4a] text-[#e8e8e8]' : 'text-[#9a9a9a] hover:text-[#e8e8e8]'
                )}
              >
                Jarvis
              </button>
              <span className="mx-1.5 h-4 w-px bg-[#4a4a4a]" />
              <button
                type="button"
                onClick={() => onGoModeChange(true)}
                className={cn(
                  'font-pixel rounded-full px-3.5 py-[3px] text-[12px] transition-colors',
                  goMode ? 'bg-[#2d7ff9] text-white' : 'text-[#9a9a9a] hover:text-[#e8e8e8]'
                )}
              >
                Jarvis GO
              </button>
            </div>
          )}

          <PromptInputAction
            tooltip={
              isLoading ? 'Stop generation'
              : isRecording ? 'Stop recording'
              : hasContent ? 'Send message'
              : enableVoice ? 'Voice message'
              : 'Type a message to send'
            }
          >
            <Button
              variant="default"
              size="icon"
              className={cn(
                'h-9 w-9 rounded-full transition-all duration-200',
                isRecording
                  ? 'bg-transparent hover:bg-[rgba(255,255,255,0.06)] text-red-500'
                  : hasContent
                  ? 'bg-[#e8e8e8] hover:bg-[#ffffff] text-[#131313]'
                  : 'bg-[#2e2e2e] hover:bg-[#3a3a3a] text-[#8a8a8a]'
              )}
              onClick={() => {
                if (isRecording) setIsRecording(false)
                else if (hasContent) handleSubmit()
                else if (enableVoice) setIsRecording(true)
              }}
              disabled={isLoading || (!hasContent && !enableVoice && !isRecording)}
            >
              {isLoading ? (
                <Square className="h-4 w-4 fill-current animate-pulse" />
              ) : isRecording ? (
                <StopCircle className="h-5 w-5 text-red-500" />
              ) : hasContent ? (
                <ArrowUp className="h-[18px] w-[18px]" strokeWidth={2.4} />
              ) : enableVoice ? (
                <Mic className="h-5 w-5" />
              ) : (
                <ArrowUp className="h-[18px] w-[18px] opacity-60" strokeWidth={2.4} />
              )}
            </Button>
          </PromptInputAction>
        </PromptInputActions>
      </PromptInput>

      <ImageViewDialog imageUrl={selectedImage} onClose={() => setSelectedImage(null)} />
    </>
  )
})
PromptInputBox.displayName = 'PromptInputBox'
