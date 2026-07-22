import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Route, BrowserRouter as Router, Routes } from "react-router-dom";
import { Github, LogOut, ScanEye, ShieldCheck } from "lucide-react";

import { RequireAuth } from "@/components/RequireAuth";
import { Button } from "@/components/ui/button";
import { useAuth, AuthProvider } from "@/hooks/useAuth";
import { DashboardPage } from "@/pages/DashboardPage";
import { LoginPage } from "@/pages/LoginPage";
import { VideoDetailPage } from "@/pages/VideoDetailPage";
import { Link } from "react-router-dom";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 5_000,
    },
  },
});

function UserMenu() {
  const { authEnabled, hasToken, user, logout } = useAuth();
  if (!authEnabled || !hasToken) return null;

  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      <ShieldCheck className="h-4 w-4" />
      <span className="hidden sm:inline">
        {user?.username} · {user?.role}
      </span>
      <Button variant="ghost" size="icon" onClick={logout} aria-label="Sign out">
        <LogOut className="h-4 w-4" />
      </Button>
    </div>
  );
}

function Header() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur">
      <div className="container flex h-16 items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/15">
            <ScanEye className="h-5 w-5 text-primary" />
          </div>
          <div className="leading-tight">
            <p className="text-sm font-bold">Video Analytics</p>
            <p className="text-xs text-muted-foreground">Offline Segmentation &amp; ROI Detection</p>
          </div>
        </Link>
        <div className="flex items-center gap-4">
          <UserMenu />
          <a
            href="https://github.com/vihaanshah191/offline-video-segmentation-and-roi-detection"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
          >
            <Github className="h-4 w-4" />
            <span className="hidden sm:inline">Source</span>
          </a>
        </div>
      </div>
    </header>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <AuthProvider>
          <div className="min-h-screen bg-background">
            <Header />
            <main className="container py-8">
              <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route
                  path="/"
                  element={
                    <RequireAuth>
                      <DashboardPage />
                    </RequireAuth>
                  }
                />
                <Route
                  path="/videos/:id"
                  element={
                    <RequireAuth>
                      <VideoDetailPage />
                    </RequireAuth>
                  }
                />
              </Routes>
            </main>
          </div>
        </AuthProvider>
      </Router>
    </QueryClientProvider>
  );
}
