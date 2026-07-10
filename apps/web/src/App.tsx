import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { getToken } from "@/api";
import { ThemeProvider } from "@/components/theme/ThemeProvider";
import { DocumentsPage } from "@/pages/DocumentsPage";
import { LoginPage } from "@/pages/LoginPage";
import { ChatPage } from "@/pages/ChatPage";

function HomeRedirect() {
  return <Navigate to={getToken() ? "/documents" : "/login"} replace />;
}

export default function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<HomeRedirect />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="*" element={<HomeRedirect />} />
        </Routes>
      </BrowserRouter>
    </ThemeProvider>
  );
}
