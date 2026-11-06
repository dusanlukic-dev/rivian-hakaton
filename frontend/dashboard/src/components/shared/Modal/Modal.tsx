import { useLayoutEffect, type MouseEventHandler, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { type AnimationDefinition, motion } from 'motion/react'
import { documentManager } from '@/utils/dom/documentManager'
import { cn } from '@/lib/utils'
import './Modal.scss'

type ModalProps = {
    className?: string
    children?: ReactNode
    animateInitial?: boolean
    onBackgroundClick?: () => void
    onAnimationComplete?: (definition: AnimationDefinition) => void
}

/** Full-screen blurred overlay rendered into <body>. To animate exit just wrap in `<AnimatePresence />` */
const Modal = ({ className, children, onBackgroundClick, animateInitial, onAnimationComplete }: ModalProps) => {
    const handleClick: MouseEventHandler<HTMLDivElement> = (e) => {
        if (e.target === e.currentTarget) onBackgroundClick?.()
    }

    useLayoutEffect(() => {
        // A nested modal must not re-measure: the scrollbar is already hidden and it would read 0
        const isFirst = !document.body.classList.contains('modal-open')
        if (isFirst) {
            // Measure before locking scroll — padding #root by this keeps the page from shifting sideways
            const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth
            document.body.style.setProperty('--scrollbar-width', `${scrollbarWidth}px`)
            document.body.classList.add('modal-open')
        }
        const lock = documentManager.lockScroll('hidden')

        return () => {
            lock.release()
            if (isFirst) {
                document.body.classList.remove('modal-open')
                document.body.style.removeProperty('--scrollbar-width')
            }
        }
    }, [])

    return createPortal(
        <motion.div className={cn('modal', className)} onClick={handleClick}
            role="dialog" aria-modal="true"
            initial={animateInitial ? { opacity: 0 } : undefined} animate={{ opacity: 1 }}
            exit={{ opacity: 0 }} transition={{ duration: .2, ease: 'easeOut' }}
            onAnimationComplete={onAnimationComplete}
        >
            {children}
        </motion.div>,
        document.body,
    )
}

export default Modal
