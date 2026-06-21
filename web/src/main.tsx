import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./index.css";
import App from "./App";
import Dashboard from "./pages/Dashboard";
import SearchResults from "./pages/SearchResults";
import Browse from "./pages/Browse";
import ConversationView from "./pages/ConversationView";
import Ask from "./pages/Ask";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 60_000, refetchOnWindowFocus: false } },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<App />}>
            <Route index element={<Dashboard />} />
            <Route path="search" element={<SearchResults />} />
            <Route path="browse" element={<Browse />} />
            <Route path="ask" element={<Ask />} />
            <Route path="c/:id" element={<ConversationView />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
