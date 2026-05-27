import { Suspense, lazy } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { I18nProvider } from "@/i18n";
import { Layout } from "@/components/Layout";

const HomePage = lazy(() => import("@/pages/HomePage").then((m) => ({ default: m.HomePage })));
const FeedRadarPage = lazy(() => import("@/pages/FeedRadarPage").then((m) => ({ default: m.FeedRadarPage })));
const ResourceDetailPage = lazy(() => import("@/pages/ResourceDetailPage").then((m) => ({ default: m.ResourceDetailPage })));
const AboutSitePage = lazy(() => import("@/pages/AboutSitePage").then((m) => ({ default: m.AboutSitePage })));
const SoftwareDownloadsPage = lazy(() =>
  import("@/pages/SoftwareDownloadsPage").then((m) => ({ default: m.SoftwareDownloadsPage })),
);
const TrendsPage = lazy(() => import("@/pages/TrendsPage").then((m) => ({ default: m.TrendsPage })));
export default function App() {
  return (
    <I18nProvider>
      <BrowserRouter>
        <Suspense fallback={<div className="px-6 py-12 text-sm text-slate-500">加载中…</div>}>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<HomePage />} />
              <Route path="trends" element={<TrendsPage />} />
              <Route path="apps" element={<FeedRadarPage key="apps" mode="apps" />} />
              <Route path="news" element={<FeedRadarPage key="news" mode="news" />} />
              <Route path="resources/:id" element={<ResourceDetailPage />} />
              <Route path="downloads" element={<SoftwareDownloadsPage />} />
              <Route path="about" element={<AboutSitePage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
    </I18nProvider>
  );
}
