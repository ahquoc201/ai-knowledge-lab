import React from "react";

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export const Input: React.FC<InputProps> = ({
  label,
  error,
  helperText,
  className = "",
  id,
  ...props
}) => {
  const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, "-") : undefined);

  return (
    <div className="w-full">
      {label && (
        <label
          htmlFor={inputId}
          className="block text-xs font-semibold text-foreground uppercase tracking-wider mb-1.5"
        >
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={`w-full rounded-md border ${
          error ? "border-status-failed-text focus:ring-status-failed-text" : "border-border focus:ring-primary"
        } bg-surface px-3 py-2 text-sm text-foreground placeholder-foreground-subtle transition-colors focus:outline-none focus:ring-2 focus:ring-offset-1 disabled:bg-background disabled:opacity-60 ${className}`}
        {...props}
      />
      {error && <p className="mt-1 text-xs text-status-failed-text font-medium">{error}</p>}
      {!error && helperText && (
        <p className="mt-1 text-xs text-foreground-subtle">{helperText}</p>
      )}
    </div>
  );
};
