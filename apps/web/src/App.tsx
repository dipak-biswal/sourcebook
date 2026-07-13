import { lazy, Suspense } from "react";
import { BrowserRouter, Link, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { getToken } from "@/api";
import { ThemeProvider } from "@/components/theme/ThemeProvider";
import { ToastProvider } from "@/components/ui/toast";
import { ErrorBoundary } from "@/components/ui/error-boundary";
import { ConfirmProvider } from "@/components/ui/confirm-dialog";
import { ProtectedRoute } from "@/components/layout/ProtectedRoute";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
});

const DashboardPage = lazy(() => import("@/pages/DashboardPage").then((m) => ({ default: m.DashboardPage })));
const DocumentsPage = lazy(() => import("@/pages/DocumentsPage").then((m) => ({ default: m.DocumentsPage })));
const LoginPage = lazy(() => import("@/pages/LoginPage").then((m) => ({ default: m.LoginPage })));
const ChatPage = lazy(() => import("@/pages/ChatPage").then((m) => ({ default: m.ChatPage })));
const UsagePage = lazy(() => import("@/pages/UsagePage").then((m) => ({ default: m.UsagePage })));
const AgentsPage = lazy(() => import("@/pages/AgentsPage").then((m) => ({ default: m.AgentsPage })));
const SettingsPage = lazy(() => import("@/pages/SettingsPage").then((m) => ({ default: m.SettingsPage })));
const NotesPage = lazy(() => import("@/pages/NotesPage").then((m) => ({ default: m.NotesPage })));

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
                <Suspense fallback={null}>
                  <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route element={<ProtectedRoute />}>
                  <Route path="/" element={<DashboardPage />} />
                  <Route path="/chat" element={<ChatPage />} />
                  <Route path="/documents" element={<DocumentsPage />} />
                  <Route path="/usage" element={<UsagePage />} />
                  <Route path="/agents" element={<AgentsPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                  <Route path="/notes" element={<NotesPage />} />
                  <Route path="/notes/:noteId" element={<NotesPage />} />
                </Route>
                <Route path="*" element={<HomeRedirect />} />
              </Routes>
                </Suspense>
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
