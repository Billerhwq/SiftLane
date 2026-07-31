import type { FormEvent, ReactNode } from "react";
import { X } from "lucide-react";
import { useModalFocus } from "../hooks/useModalFocus";

export function Dialog({
  open,
  title,
  children,
  submitLabel,
  busy,
  onClose,
  onSubmit,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  submitLabel: string;
  busy?: boolean;
  onClose: () => void;
  onSubmit: () => void;
}) {
  const dialogRef = useModalFocus<HTMLFormElement>(open, onClose);
  if (!open) return null;
  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit();
  }
  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <form ref={dialogRef} className="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title" onSubmit={submit}>
        <header><strong id="dialog-title">{title}</strong><button type="button" className="icon-button" onClick={onClose} aria-label="关闭"><X size={16} /></button></header>
        <div className="dialog__body">{children}</div>
        <footer><button type="button" className="button" onClick={onClose}>取消</button><button type="submit" className="button primary" disabled={busy}>{busy ? "处理中" : submitLabel}</button></footer>
      </form>
    </div>
  );
}
