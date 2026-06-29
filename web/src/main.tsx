import React, { Suspense, lazy, type ReactNode } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./index.css";
import App from "./App";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const SearchResults = lazy(() => import("./pages/SearchResults"));
const Browse = lazy(() => import("./pages/Browse"));
const ConversationView = lazy(() => import("./pages/ConversationView"));
const Ask = lazy(() => import("./pages/Ask"));
const Plan = lazy(() => import("./pages/Plan"));

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 60_000, refetchOnWindowFocus: false } },
});

function RouteFallback() {
  return <div className="py-24 text-center font-mono text-sm text-faint">載入中…</div>;
}

function LazyPage({ children }: { children: ReactNode }) {
  return <Suspense fallback={<RouteFallback />}>{children}</Suspense>;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<App />}>
            <Route index element={<LazyPage><Dashboard /></LazyPage>} />
            <Route path="search" element={<LazyPage><SearchResults /></LazyPage>} />
            <Route path="browse" element={<LazyPage><Browse /></LazyPage>} />
            <Route path="ask" element={<LazyPage><Ask /></LazyPage>} />
            <Route path="plan" element={<LazyPage><Plan /></LazyPage>} />
            <Route path="c/:id" element={<LazyPage><ConversationView /></LazyPage>} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
