import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";

const MODAL_ANIMATION_DURATION = 250;

interface ModalProps {
  open: boolean;
  onClose: () => void;
  titleId: string;
  children: ReactNode;
  panelClassName?: string;
  overlayClassName?: string;
  motion?: "modal" | "drawer";
}

const focusableSelector = [
  "a[href]",
  "area[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex=\"-1\"])",
].join(",");

export function Modal({
  open,
  onClose,
  titleId,
  children,
  panelClassName,
  overlayClassName,
  motion = "modal",
}: ModalProps) {
  const [mounted, setMounted] = useState(open);
  const [visible, setVisible] = useState(open);
  const mountedRef = useRef(open);
  const panelRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  const closeTimerRef = useRef<number | null>(null);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (open) {
      if (closeTimerRef.current !== null) {
        window.clearTimeout(closeTimerRef.current);
        closeTimerRef.current = null;
      }

      if (!mountedRef.current) {
        mountedRef.current = true;
        setMounted(true);
        setVisible(false);
        const frame = window.requestAnimationFrame(() => setVisible(true));
        return () => window.cancelAnimationFrame(frame);
      }

      setVisible(true);
      return;
    }

    if (!mountedRef.current) return;

    setVisible(false);
    closeTimerRef.current = window.setTimeout(() => {
      mountedRef.current = false;
      closeTimerRef.current = null;
      setMounted(false);
    }, MODAL_ANIMATION_DURATION);

    return () => {
      if (closeTimerRef.current !== null) {
        window.clearTimeout(closeTimerRef.current);
        closeTimerRef.current = null;
      }
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const root = document.getElementById("root");
    const previousAriaHidden = root?.getAttribute("aria-hidden") ?? null;
    if (root) {
      root.setAttribute("aria-hidden", "true");
      root.inert = true;
    }

    const focusFirstElement = () => {
      const panel = panelRef.current;
      const first = panel?.querySelector<HTMLElement>(focusableSelector);
      (first || panel)?.focus();
    };
    const frame = window.requestAnimationFrame(focusFirstElement);
    const handleKeyDown = (event: KeyboardEvent) => {
      const panel = panelRef.current;
      if (!panel) return;
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = [...panel.querySelectorAll<HTMLElement>(focusableSelector)];
      if (focusable.length === 0) {
        event.preventDefault();
        panel.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("keydown", handleKeyDown);
      if (root) {
        root.inert = false;
        if (previousAriaHidden === null) root.removeAttribute("aria-hidden");
        else root.setAttribute("aria-hidden", previousAriaHidden);
      }
      if (previousFocusRef.current?.isConnected) previousFocusRef.current.focus();
    };
  }, [open]);

  if (!mounted) return null;

  const animationState = visible ? "open" : "closed";

  return createPortal(
    <div
      className={cn("app-modal-overlay fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4", overlayClassName)}
      data-state={animationState}
      onClick={(event) => {
        if (event.target === event.currentTarget) onCloseRef.current();
      }}
    >
      <div
        ref={panelRef}
        className={cn("app-modal-panel max-h-[90vh] w-full overflow-auto rounded-lg border bg-card p-6 shadow-lg", panelClassName)}
        data-motion={motion}
        data-state={animationState}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
