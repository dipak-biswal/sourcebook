import { useState, type FormEvent } from "react";
import { Loader2, Mail, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { FieldError } from "@/components/ui/field-error";
import { Input } from "@/components/ui/input";
import { validateEmail } from "@/lib/validation";
import { useSettingsPage } from "./SettingsPageContext";

export function SettingsProfileForm() {
  const { email, savingProfile, onEmailChange, onUpdateProfile } = useSettingsPage();
  const [error, setError] = useState<string | undefined>();
  const [touched, setTouched] = useState(false);

  function handleChange(v: string) {
    onEmailChange(v);
    if (touched) setError(validateEmail(v) ?? undefined);
  }

  function handleBlur() {
    setTouched(true);
    setError(validateEmail(email) ?? undefined);
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    const err = validateEmail(email);
    setError(err ?? undefined);
    if (err) return;
    void onUpdateProfile();
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-vercel-md border border-hairline bg-canvas p-4"
      noValidate
    >
      <h2 className="text-sm font-semibold text-ink">Profile</h2>
      <p className="mt-1 text-xs text-mute">
        Update your email address.
      </p>

      <label className="mt-3 block">
        <span className="mb-1 flex items-center gap-1 text-xs text-mute">
          <Mail className="h-3 w-3" strokeWidth={1.5} />
          Email <span className="text-danger-text">*</span>
        </span>
        <Input
          value={email}
          onChange={(e) => handleChange(e.target.value)}
          onBlur={handleBlur}
          type="email"
          placeholder="you@example.com"
          aria-invalid={!!error || undefined}
        />
        <FieldError error={error} />
      </label>

      <Button
        type="submit"
        className="mt-3 rounded-[6px]"
        disabled={savingProfile || !email.trim()}
      >
        {savingProfile ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Save className="h-4 w-4" strokeWidth={1.5} />
        )}
        Save
      </Button>
    </form>
  );
}
