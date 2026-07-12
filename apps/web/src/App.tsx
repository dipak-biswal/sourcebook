import { BrowserRouter, Link, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { getToken } from "@/api";
import { ThemeProvider } from "@/components/theme/ThemeProvider";
import { ToastProvider } from "@/components/ui/toast";
import { ErrorBoundary } from "@/components/ui/error-boundary";
import { ConfirmProvider } from "@/components/ui/confirm-dialog";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
});
import { DashboardPage } from "@/pages/DashboardPage";
import { DocumentsPage } from "@/pages/DocumentsPage";
import { LoginPage } from "@/pages/LoginPage";
import { ChatPage } from "@/pages/ChatPage";
import { UsagePage } from "@/pages/UsagePage";
import { AgentsPage } from "@/pages/AgentsPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { NotesPage } from "@/pages/NotesPage";

function HomeRedirect() {
  return <Navigate to={getToken() ? "/" : "/login"} replace />;
}

export default function App() {
  return (
    <ThemeProvider>
      <ToastProvider>
        <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <SkipLink />
          <ErrorBoundary>
            <ConfirmProvider>
              <Routes>
                <Route path="/" element={<DashboardPage />} />
                <Route path="/login" element={<LoginPage />} />
                <Route path="/chat" element={<ChatPage />} />
                <Route path="/documents" element={<DocumentsPage />} />
              <Route path="/usage" element={<UsagePage />} />
              <Route path="/agents" element={<AgentsPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/notes" element={<NotesPage />} />
              <Route path="/notes/:noteId" element={<NotesPage />} />
              <Route path="*" element={<HomeRedirect />} />
              </Routes>
            </ConfirmProvider>
          </ErrorBoundary>
        </BrowserRouter>
        </QueryClientProvider>
      </ToastProvider>
    </ThemeProvider>
  );
}

function SkipLink() {
  return (
    <Link
      to="#main-content"
      className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-[6px] focus:bg-ink focus:p-3 focus:text-sm focus:font-medium focus:text-[var(--canvas)] focus:shadow-lg focus:outline-none"
      onClick={(e) => {
        e.preventDefault();
        document.getElementById("main-content")?.focus();
      }}
    >
      Skip to main content
    </Link>
  );
}
