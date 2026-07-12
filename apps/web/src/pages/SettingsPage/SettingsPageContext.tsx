import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api, getToken, setCachedUser, type Workspace } from "@/api";
import { useToast } from "@/components/ui/toast";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { confirmAction } from "@/lib/confirm";
import { formatError } from "@/lib/utils";

type SettingsPageContextValue = {
  email: string;
  error: string | null;
  savingProfile: boolean;
  savingPassword: boolean;
  currentPassword: string;
  newPassword: string;
  confirmPassword: string;
  workspaces: Workspace[];
  newWsName: string;
  creatingWs: boolean;
  renamingId: string | null;
  renameValue: string;
  savingRename: boolean;
  onEmailChange: (v: string) => void;
  onUpdateProfile: () => Promise<void>;
  onCurrentPasswordChange: (v: string) => void;
  onNewPasswordChange: (v: string) => void;
  onConfirmPasswordChange: (v: string) => void;
  onChangePassword: () => Promise<void>;
  onNewWsNameChange: (v: string) => void;
  onCreateWorkspace: () => Promise<void>;
  onStartRename: (id: string, name: string) => void;
  onRenameValueChange: (v: string) => void;
  onCancelRename: () => void;
  onSaveRename: (id: string) => Promise<void>;
  onDeleteWorkspace: (id: string) => Promise<void>;
  onLogout: () => void;
};

const SettingsPageContext = createContext<SettingsPageContextValue | null>(null);

export function SettingsPageProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const { success, error: toastError } = useToast();
  useDocumentTitle("Settings");

  const [email, setEmail] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [savingProfile, setSavingProfile] = useState(false);
  const [savingPassword, setSavingPassword] = useState(false);

  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [newWsName, setNewWsName] = useState("");
  const [creatingWs, setCreatingWs] = useState(false);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [savingRename, setSavingRename] = useState(false);

  useEffect(() => {
    if (!getToken()) return;
    api.me()
      .then((u) => { setEmail(u.email); })
      .catch((err) => setError(formatError(err)));
    loadWorkspaces();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadWorkspaces() {
    try {
      setWorkspaces(await api.workspaces());
    } catch { /* ignore */ }
  }

  async function onUpdateProfile() {
    if (!email.trim() || savingProfile) return;
    setSavingProfile(true);
    setError(null);
    try {
      const updated = await api.updateProfile(email.trim());
      setCachedUser(updated);
      success("Profile updated");
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Update failed", msg);
    } finally {
      setSavingProfile(false);
    }
  }

  async function onChangePassword() {
    if (!currentPassword || !newPassword || savingPassword) return;
    setSavingPassword(true);
    setError(null);
    try {
      await api.changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      success("Password changed");
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Password change failed", msg);
    } finally {
      setSavingPassword(false);
    }
  }

  async function onCreateWorkspace() {
    const name = newWsName.trim();
    if (!name || creatingWs) return;
    setCreatingWs(true);
    setError(null);
    try {
      await api.createWorkspace(name);
      setNewWsName("");
      success(`Workspace "${name}" created`);
      await loadWorkspaces();
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Create failed", msg);
    } finally {
      setCreatingWs(false);
    }
  }

  async function onSaveRename(id: string) {
    const name = renameValue.trim();
    if (!name || savingRename) return;
    setSavingRename(true);
    setError(null);
    try {
      await api.updateWorkspace(id, name);
      setRenamingId(null);
      setRenameValue("");
      success("Workspace renamed");
      await loadWorkspaces();
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Rename failed", msg);
    } finally {
      setSavingRename(false);
    }
  }

  async function onDeleteWorkspace(id: string) {
    const ws = workspaces.find((w) => w.id === id);
    if (!(await confirmAction(
      "Delete workspace?",
      ws ? `"${ws.name}" and all its documents, chats, and agent runs will be deleted.` : "This cannot be undone.",
      "Delete workspace",
    ))) return;
    setError(null);
    try {
      await api.deleteWorkspace(id);
      success("Workspace deleted");
      await loadWorkspaces();
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Delete failed", msg);
    }
  }

  const value: SettingsPageContextValue = {
    email, error, savingProfile, savingPassword,
    currentPassword, newPassword, confirmPassword,
    workspaces, newWsName, creatingWs, renamingId, renameValue, savingRename,
    onEmailChange: setEmail,
    onUpdateProfile,
    onCurrentPasswordChange: setCurrentPassword,
    onNewPasswordChange: setNewPassword,
    onConfirmPasswordChange: setConfirmPassword,
    onChangePassword,
    onNewWsNameChange: setNewWsName,
    onCreateWorkspace,
    onStartRename: (id, name) => { setRenamingId(id); setRenameValue(name); },
    onRenameValueChange: setRenameValue,
    onCancelRename: () => setRenamingId(null),
    onSaveRename,
    onDeleteWorkspace,
    onLogout: () => navigate("/login", { replace: true }),
  };

  return (
    <SettingsPageContext.Provider value={value}>
      {children}
    </SettingsPageContext.Provider>
  );
}

export function useSettingsPage(): SettingsPageContextValue {
  const ctx = useContext(SettingsPageContext);
  if (!ctx) throw new Error("useSettingsPage must be used within SettingsPageProvider");
  return ctx;
}
