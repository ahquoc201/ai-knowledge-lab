import React from "react";
import { AlertCircle, CheckCircle2, Info, AlertTriangle, X } from "lucide-react";

interface AlertProps {
  type?: "info" | "success" | "warning" | "error";
  title?: string;
  children: React.ReactNode;
  onClose?: () => void;
  className?: string;
}

export const Alert: React.FC<AlertProps> = ({
  type = "info",
  title,
  children,
  onClose,
  className = "",
}) => {
  const styles = {
    info: {
      container: "bg-blue-50 border-blue-200 text-blue-900",
      icon: <Info className="h-5 w-5 text-blue-600 flex-shrink-0" />,
    },
    success: {
      container: "bg-status-ready-bg border-status-ready-border text-emerald-900",
      icon: <CheckCircle2 className="h-5 w-5 text-status-ready-text flex-shrink-0" />,
    },
    warning: {
      container: "bg-status-pending-bg border-status-pending-border text-amber-900",
      icon: <AlertTriangle className="h-5 w-5 text-status-pending-text flex-shrink-0" />,
    },
    error: {
      container: "bg-status-failed-bg border-status-failed-border text-red-900",
      icon: <AlertCircle className="h-5 w-5 text-status-failed-text flex-shrink-0" />,
    },
  };

  const current = styles[type];

  return (
    <div
      role="alert"
      className={`flex items-start gap-3 rounded-lg border p-4 text-sm ${current.container} ${className}`}
    >
      {current.icon}
      <div className="flex-1">
        {title && <h4 className="font-semibold mb-1">{title}</h4>}
        <div className="text-xs leading-relaxed opacity-90">{children}</div>
      </div>
      {onClose && (
        <button
          onClick={onClose}
          className="text-foreground-subtle hover:text-foreground transition-colors -mr-1 -mt-1 p-1 rounded"
          aria-label="Close alert"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
};
