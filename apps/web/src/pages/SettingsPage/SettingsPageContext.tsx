import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api, setCachedUser } from "@/api";
import { useToast } from "@/components/ui/toast";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { useMe, useWorkspaces } from "@/hooks/queries";
import { confirmAction } from "@/lib/confirm";
import { formatError } from "@/lib/utils";
import type { SettingsPageContextValue } from "@/types/settings";
import { SettingsPageContext } from "./settings-page-context";

export function SettingsPageProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { success, error: toastError } = useToast();
  useDocumentTitle("Settings");

  const { data: user } = useMe();
  const { data: workspaces = [] } = useWorkspaces();

  const [email, setEmail] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [savingProfile, setSavingProfile] = useState(false);
  const [savingPassword, setSavingPassword] = useState(false);

  const [newWsName, setNewWsName] = useState("");
  const [creatingWs, setCreatingWs] = useState(false);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [savingRename, setSavingRename] = useState(false);

  useEffect(() => {
    if (user?.email) setEmail(user.email);
  }, [user?.email]);

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

  function invalidateWorkspaces() {
    queryClient.invalidateQueries({ queryKey: ["workspaces"] });
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
      invalidateWorkspaces();
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
      invalidateWorkspaces();
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
      invalidateWorkspaces();
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
