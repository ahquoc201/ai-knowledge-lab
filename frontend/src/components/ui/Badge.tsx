import React from "react";
import { DocumentStatus } from "../../types";

interface BadgeProps {
  status?: DocumentStatus | "default" | "info";
  children: React.ReactNode;
  className?: string;
  size?: "sm" | "md";
}

export const Badge: React.FC<BadgeProps> = ({
  status = "default",
  children,
  className = "",
  size = "md",
}) => {
  const sizeStyles = {
    sm: "px-2 py-0.5 text-xs font-medium",
    md: "px-2.5 py-1 text-xs font-semibold",
  };

  const statusStyles: Record<string, string> = {
    ready: "bg-status-ready-bg text-status-ready-text border-status-ready-border",
    processing: "bg-status-processing-bg text-status-processing-text border-status-processing-border animate-pulse",
    pending: "bg-status-pending-bg text-status-pending-text border-status-pending-border",
    failed: "bg-status-failed-bg text-status-failed-text border-status-failed-border",
    info: "bg-primary-subtle text-primary border-blue-200",
    default: "bg-background text-foreground-muted border-border",
  };

  const currentStatusStyle = statusStyles[status] || statusStyles.default;

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border ${sizeStyles[size]} ${currentStatusStyle} ${className}`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          status === "ready"
            ? "bg-status-ready-text"
            : status === "processing"
            ? "bg-status-processing-text"
            : status === "pending"
            ? "bg-status-pending-text"
            : status === "failed"
            ? "bg-status-failed-text"
            : "bg-foreground-subtle"
        }`}
      />
      {children}
    </span>
  );
};
