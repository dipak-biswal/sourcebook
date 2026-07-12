export function validateEmail(v: string): string | null {
  if (!v.trim()) return "Email is required";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.trim())) return "Enter a valid email address";
  return null;
}

export function validateRequired(v: string, label: string): string | null {
  if (!v.trim()) return `${label} is required`;
  return null;
}

export function validatePassword(v: string): string | null {
  if (!v) return "Password is required";
  if (v.length < 8) return "Password must be at least 8 characters";
  return null;
}

export function validatePasswordMatch(v: string, match: string): string | null {
  if (!v) return "Confirm your password";
  if (v !== match) return "Passwords do not match";
  return null;
}

export function validateWorkspaceName(v: string): string | null {
  if (!v.trim()) return "Workspace name is required";
  if (v.trim().length < 2) return "Name must be at least 2 characters";
  return null;
}

export function validateNoteTitle(v: string): string | null {
  if (!v.trim()) return "Title is required";
  return null;
}
