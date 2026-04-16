import { Suspense, lazy } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { I18nProvider } from "@/i18n";
import { Layout } from "@/components/Layout";

const Home = lazy(() => import("@/pages/Home").then((m) => ({ default: m.Home })));
const TrendsPage = lazy(() => import("@/pages/TrendsPage").then((m) => ({ default: m.TrendsPage })));
const TrendDetailPage = lazy(() => import("@/pages/TrendDetailPage").then((m) => ({ default: m.TrendDetailPage })));
const InspirationsPage = lazy(() => import("@/pages/InspirationsPage").then((m) => ({ default: m.InspirationsPage })));
const BriefingPage = lazy(() => import("@/pages/BriefingPage").then((m) => ({ default: m.BriefingPage })));
const EvidencePage = lazy(() => import("@/pages/EvidencePage").then((m) => ({ default: m.EvidencePage })));
const CategoriesPage = lazy(() => import("@/pages/CategoriesPage").then((m) => ({ default: m.CategoriesPage })));
const MethodologyPage = lazy(() => import("@/pages/MethodologyPage").then((m) => ({ default: m.MethodologyPage })));
const LegalHub = lazy(() => import("@/pages/LegalPages").then((m) => ({ default: m.LegalHub })));
const LegalPrivacy = lazy(() => import("@/pages/LegalPages").then((m) => ({ default: m.LegalPrivacy })));
const LegalTerms = lazy(() => import("@/pages/LegalPages").then((m) => ({ default: m.LegalTerms })));
const LegalSources = lazy(() => import("@/pages/LegalPages").then((m) => ({ default: m.LegalSources })));
const RemovalPage = lazy(() => import("@/pages/RemovalPage").then((m) => ({ default: m.RemovalPage })));
export default function App() {
  return (
    <I18nProvider>
      <BrowserRouter>
        <Suspense fallback={<div className="px-6 py-12 text-sm text-slate-400">Loading…</div>}>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<Home />} />
              <Route path="trends" element={<TrendsPage />} />
              <Route path="trends/:trendKey" element={<TrendDetailPage />} />
              <Route path="inspirations" element={<InspirationsPage />} />
              <Route path="briefing" element={<BriefingPage />} />
              <Route path="evidence/:signalId" element={<EvidencePage />} />
              <Route path="categories" element={<CategoriesPage />} />
              <Route path="methodology" element={<MethodologyPage />} />
              <Route path="legal" element={<LegalHub />} />
              <Route path="legal/privacy" element={<LegalPrivacy />} />
              <Route path="legal/terms" element={<LegalTerms />} />
              <Route path="legal/data-sources" element={<LegalSources />} />
              <Route path="legal/removal-request" element={<RemovalPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
    </I18nProvider>
  );
}
