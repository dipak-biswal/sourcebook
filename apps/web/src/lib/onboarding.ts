export type OnboardingStepId = "upload" | "ingest" | "chat";

export type OnboardingStep = {
  id: OnboardingStepId;
  label: string;
  description: string;
  href: string;
  done: boolean;
};

export function checklistDismissKey(workspaceId: string): string {
  return `sourcebook_onboarding_checklist_${workspaceId}`;
}

export function isChecklistDismissed(workspaceId: string): boolean {
  try {
    return localStorage.getItem(checklistDismissKey(workspaceId)) === "1";
  } catch {
    return false;
  }
}

export function dismissChecklist(workspaceId: string): void {
  try {
    localStorage.setItem(checklistDismissKey(workspaceId), "1");
  } catch {
    /* ignore */
  }
}