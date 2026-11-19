"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { ThemeProvider } from "@/lib/theme";
import { LoadingBar } from "@/components/loading-bar";

export function QueryProvider({ children }: { children: React.ReactNode }) {
  // A minute before refetching what is already on screen: going back and
  // forth between sections shows the last answer at once.
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { staleTime: 60_000, refetchOnWindowFocus: false } } }));
  return (
    <QueryClientProvider client={client}>
      <LoadingBar />
      {children}
    </QueryClientProvider>
  );
}

export function AppProviders({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <QueryProvider>{children}</QueryProvider>
    </ThemeProvider>
  );
}
