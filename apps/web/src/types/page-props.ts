import type { UsageSummary, Document, Workspace, DevUserList } from "@/api";

export type UsagePageViewProps = {
  data: UsageSummary | null;
  error: string | null;
  loading: boolean;
  onRefresh: () => void;
  onLogout: () => void;
};

export type DocumentsPageViewProps = {
  workspaces: Workspace[];
  workspaceId: string;
  docs: Document[];
  error: string | null;
  uploading: boolean;
  ingestingId: string | null;
  ingestProgress: string | null;
  loading: boolean;
  onChangeWorkspace: (id: string) => void;
  onRefreshWorkspaces: () => void;
  onUpload: (file: File) => void;
  onDelete: (id: string) => void;
  onIngest: (id: string) => void;
  onNavigateToChat: () => void;
  onLogout: () => void;
};

export type LoginPageViewProps = {
  error: string | null;
  busy: boolean;
  devInfo: DevUserList | null;
  devError: string | null;
  devBusy: boolean;
  email: string;
  password: string;
  onEmailChange: (v: string) => void;
  onPasswordChange: (v: string) => void;
  onSubmit: (e: React.FormEvent, mode: "login" | "register") => void;
  onFillLogin: (email: string, password: string | null) => void;
  onSetPassword: (email: string) => void;
  onSetAllPasswords: () => void;
  onLoadDevUsers: () => void;
};
