import React from "react";

interface CardProps {
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
}

export const Card: React.FC<CardProps> = ({ children, className = "", onClick }) => (
  <div
    onClick={onClick}
    className={`bg-surface rounded-lg border border-border p-5 shadow-sm transition-all ${
      onClick ? "cursor-pointer hover:border-primary/50 hover:shadow" : ""
    } ${className}`}
  >
    {children}
  </div>
);

export const CardHeader: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = "",
}) => <div className={`border-b border-border pb-3 mb-4 ${className}`}>{children}</div>;

export const CardTitle: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = "",
}) => <h3 className={`text-base font-semibold text-foreground ${className}`}>{children}</h3>;

export const CardDescription: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = "",
}) => <p className={`text-xs text-foreground-muted mt-0.5 ${className}`}>{children}</p>;
