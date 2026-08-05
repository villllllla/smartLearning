import { Navigate, Route, Routes, useLocation } from "react-router-dom";



import { AppLayout } from "@/components/layout/AppLayout";

import { useAuth } from "@/lib/AuthContext";



import { BankPage } from "@/pages/bank/BankPage";

import { CandidateBatchesPage } from "@/pages/bank/CandidateBatchesPage";
import { CandidatesPage } from "@/pages/bank/CandidatesPage";

import { ChatPage } from "@/pages/chat/ChatPage";

import { AiNewsPage } from "@/pages/ai-news/AiNewsPage";
import { LoginPage } from "@/pages/auth/LoginPage";
import { RegisterPage } from "@/pages/auth/RegisterPage";
import { GoalsPage } from "@/pages/goals/GoalsPage";
import { LearningNotesPage } from "@/pages/learning/LearningNotesPage";
import { PracticeRunPage } from "@/pages/practice/PracticeRunPage";

import { PracticeSetupPage } from "@/pages/practice/PracticeSetupPage";

import { SettingsPage } from "@/pages/settings/SettingsPage";
import { TodosPage } from "@/pages/todos/TodosPage";
import { LongTermTodosPage } from "@/pages/todos/LongTermTodosPage";

import { WikiDetailPage } from "@/pages/wiki/WikiDetailPage";

import { WikiListPage } from "@/pages/wiki/WikiListPage";

import { WikiUploadPage } from "@/pages/wiki/WikiUploadPage";



function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, authEnabled, loading } = useAuth();
  const location = useLocation();



  if (loading) {

    return (

      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">

        加载中…

      </div>

    );

  }



  if (authEnabled && (!user || user.id === 0)) {

    const next = `${location.pathname}${location.search}`;

    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />;

  }



  return <>{children}</>;

}



export default function App() {

  return (

    <Routes>

      {/* These must render the real pages: RequireAuth sends unauthenticated
          users to /login, so short-circuiting it back to /wiki produced an
          infinite redirect (and a blank screen) as soon as auth was enabled.
          LoginPage itself redirects onward when auth is off. */}

      <Route path="/login" element={<LoginPage />} />

      <Route path="/register" element={<RegisterPage />} />



      <Route

        element={

          <RequireAuth>

            <AppLayout />

          </RequireAuth>

        }

      >

        <Route index element={<Navigate to="/wiki" replace />} />



        <Route path="/wiki" element={<WikiListPage />} />

        <Route path="/wiki/upload" element={<WikiUploadPage />} />

        <Route path="/wiki/:id" element={<WikiDetailPage />} />



        <Route path="/chat" element={<ChatPage />} />



        <Route path="/bank" element={<BankPage />} />

        <Route path="/bank/candidate-batches" element={<CandidateBatchesPage />} />

        <Route path="/bank/candidates/:batchId" element={<CandidatesPage />} />



        <Route path="/practice" element={<PracticeSetupPage />} />

        <Route path="/practice/run" element={<PracticeRunPage />} />

        <Route path="/goals" element={<GoalsPage />} />

        <Route path="/learning" element={<LearningNotesPage />} />

        <Route path="/ai-news" element={<AiNewsPage />} />

        <Route path="/todos" element={<TodosPage />} />
        <Route path="/todos/long-term" element={<LongTermTodosPage />} />

        <Route path="/settings/*" element={<SettingsPage />} />



        <Route path="*" element={<Navigate to="/wiki" replace />} />

      </Route>

    </Routes>

  );

}


