import { Suspense, lazy } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { I18nProvider } from "@/i18n";
import { Layout } from "@/components/Layout";
import { TrendBoardPage } from "@/pages/TrendBoardPage";

const ResourcesPage = lazy(() => import("@/pages/ResourcesPage").then((m) => ({ default: m.ResourcesPage })));
const ResourceDetailPage = lazy(() => import("@/pages/ResourceDetailPage").then((m) => ({ default: m.ResourceDetailPage })));
const AboutSitePage = lazy(() => import("@/pages/AboutSitePage").then((m) => ({ default: m.AboutSitePage })));

export default function App() {
  return (
    <I18nProvider>
      <BrowserRouter>
        <Suspense fallback={<div className="px-6 py-12 text-sm text-slate-400">Loading…</div>}>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<Navigate to="/trends" replace />} />
              <Route path="trends" element={<TrendBoardPage />} />
              <Route path="resources" element={<ResourcesPage />} />
              <Route path="resources/:id" element={<ResourceDetailPage />} />
              <Route path="about" element={<AboutSitePage />} />
              <Route path="*" element={<Navigate to="/trends" replace />} />
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
    </I18nProvider>
  );
}
