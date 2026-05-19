import { FormEvent } from "react";

type Props = {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
};

export default function Composer({ value, onChange, onSubmit, disabled }: Props) {
  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!value.trim() || disabled) return;
    onSubmit();
  }

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Message Symposa…"
        rows={2}
        disabled={disabled}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSubmit(e);
          }
        }}
      />
      <button type="submit" disabled={disabled || !value.trim()}>
        Send
      </button>
    </form>
  );
}
