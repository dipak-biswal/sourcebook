import { useState, type FormEvent } from "react";
import { KeyRound, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { FieldError } from "@/components/ui/field-error";
import { Input } from "@/components/ui/input";
import { validateRequired, validatePassword, validatePasswordMatch } from "@/lib/validation";
import { useSettingsPage } from "./settings-page-context";

export function SettingsPasswordForm() {
  const {
    currentPassword, newPassword, confirmPassword,
    savingPassword,
    onCurrentPasswordChange, onNewPasswordChange, onConfirmPasswordChange,
    onChangePassword,
  } = useSettingsPage();
  const [errors, setErrors] = useState<{ current?: string; newPw?: string; confirm?: string }>({});
  const [touched, setTouched] = useState(false);

  function setField(field: "current" | "newPw" | "confirm", value: string, setter: (v: string) => void) {
    setter(value);
    if (!touched) return;
    const e: typeof errors = {};
    if (field === "current") e.current = validateRequired(value, "Current password") ?? undefined;
    else if (field === "newPw") e.newPw = validatePassword(value) ?? undefined;
    else if (field === "confirm") e.confirm = validatePasswordMatch(value, newPassword) ?? undefined;
    setErrors((prev) => ({ ...prev, ...e }));
  }

  function validate(): boolean {
    const current = validateRequired(currentPassword, "Current password");
    const newPw = validatePassword(newPassword);
    const confirm = validatePasswordMatch(confirmPassword, newPassword);
    setErrors({ current: current ?? undefined, newPw: newPw ?? undefined, confirm: confirm ?? undefined });
    return !(current ?? newPw ?? confirm);
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!validate()) return;
    void onChangePassword();
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-vercel-md border border-hairline bg-canvas p-4"
      noValidate
    >
      <h2 className="text-sm font-semibold text-ink">Change password</h2>
      <p className="mt-1 text-xs text-mute">
        Enter your current password and a new one.
      </p>

      <label className="mt-3 block">
        <span className="mb-1 flex items-center gap-1 text-xs text-mute">
          <KeyRound className="h-3 w-3" strokeWidth={1.5} />
          Current password <span className="text-danger-text">*</span>
        </span>
        <Input
          value={currentPassword}
          onChange={(e) => setField("current", e.target.value, onCurrentPasswordChange)}
          type="password"
          placeholder="Current password"
          aria-invalid={!!errors.current || undefined}
        />
        <FieldError error={errors.current} />
      </label>

      <label className="mt-3 block">
        <span className="mb-1 text-xs text-mute">
          New password <span className="text-danger-text">*</span>
        </span>
        <Input
          value={newPassword}
          onChange={(e) => setField("newPw", e.target.value, onNewPasswordChange)}
          type="password"
          placeholder="New password (min 8 chars)"
          aria-invalid={!!errors.newPw || undefined}
        />
        <FieldError error={errors.newPw} />
      </label>

      <label className="mt-3 block">
        <span className="mb-1 text-xs text-mute">
          Confirm new password <span className="text-danger-text">*</span>
        </span>
        <Input
          value={confirmPassword}
          onChange={(e) => setField("confirm", e.target.value, onConfirmPasswordChange)}
          type="password"
          placeholder="Confirm new password"
          aria-invalid={!!errors.confirm || undefined}
        />
        <FieldError error={errors.confirm} />
      </label>

      <Button
        type="submit"
        className="mt-3 rounded-[6px]"
        disabled={savingPassword || !currentPassword || !newPassword || !confirmPassword}
      >
        {savingPassword ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <KeyRound className="h-4 w-4" strokeWidth={1.5} />
        )}
        Change password
      </Button>
    </form>
  );
}
