import { useEffect, useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import {
  api,
  getToken,
  setCachedUser,
  type Workspace,
} from "@/api";
import { useToast } from "@/components/ui/toast";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { confirmAction } from "@/lib/confirm";
import { formatError } from "@/lib/utils";
import { SettingsPageView } from "./view";

export { SettingsPageView } from "./view";

export function SettingsPage() {
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
      .then((u) => {
        setEmail(u.email);
      })
      .catch((err) => setError(formatError(err)));
    loadWorkspaces();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadWorkspaces() {
    try {
      setWorkspaces(await api.workspaces());
    } catch { /* ignore */ }
  }

  if (!getToken()) {
    return <Navigate to="/login" replace />;
  }

  async function onUpdateProfile(e: FormEvent) {
    e.preventDefault();
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

  async function onChangePassword(e: FormEvent) {
    e.preventDefault();
    if (!currentPassword || !newPassword || savingPassword) return;
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    if (newPassword.length < 8) {
      setError("New password must be at least 8 characters");
      return;
    }
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

  return (
    <SettingsPageView
      email={email}
      error={error}
      savingProfile={savingProfile}
      savingPassword={savingPassword}
      currentPassword={currentPassword}
      newPassword={newPassword}
      confirmPassword={confirmPassword}
      workspaces={workspaces}
      newWsName={newWsName}
      creatingWs={creatingWs}
      renamingId={renamingId}
      renameValue={renameValue}
      savingRename={savingRename}
      onEmailChange={setEmail}
      onUpdateProfile={onUpdateProfile}
      onCurrentPasswordChange={setCurrentPassword}
      onNewPasswordChange={setNewPassword}
      onConfirmPasswordChange={setConfirmPassword}
      onChangePassword={onChangePassword}
      onNewWsNameChange={setNewWsName}
      onCreateWorkspace={onCreateWorkspace}
      onStartRename={(id, name) => { setRenamingId(id); setRenameValue(name); }}
      onRenameValueChange={setRenameValue}
      onCancelRename={() => setRenamingId(null)}
      onSaveRename={onSaveRename}
      onDeleteWorkspace={onDeleteWorkspace}
      onLogout={() => navigate("/login", { replace: true })}
    />
  );
}
