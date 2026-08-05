import { FormEvent, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { UserPlus } from "lucide-react";

import { ApiError } from "@/api/client";
import { authApi } from "@/api/auth";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { saveAuth } from "@/lib/auth";
import { useAuth } from "@/lib/AuthContext";

export function RegisterPage() {
  const { user, loading, refresh } = useAuth();
  const navigate = useNavigate();

  const [tenantName, setTenantName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (!loading && user && user.id > 0) {
    return <Navigate to="/wiki" replace />;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const res = await authApi.register({
        tenant_name: tenantName.trim(),
        email: email.trim(),
        password,
        display_name: displayName.trim() || undefined,
      });
      saveAuth(res.access_token, res.user);
      await refresh();
      navigate("/wiki", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "注册失败，请重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-muted/30 p-6">
      <Card className="w-full max-w-md shadow-lg">
        <CardContent className="space-y-6 p-8">
          <div className="space-y-1 text-center">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
              <UserPlus className="h-6 w-6" />
            </div>
            <h1 className="text-2xl font-bold tracking-tight">注册新租户</h1>
            <p className="text-sm text-muted-foreground">创建独立工作区，数据与其他租户隔离</p>
          </div>

          <form className="space-y-4" onSubmit={onSubmit}>
            <div className="space-y-2">
              <Label htmlFor="tenant">租户名称</Label>
              <Input
                id="tenant"
                value={tenantName}
                onChange={(e) => setTenantName(e.target.value)}
                placeholder="我的团队"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="display">显示名称（可选）</Label>
              <Input
                id="display"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="张三"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">管理员邮箱</Label>
              <Input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">密码</Label>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={8}
                required
              />
            </div>
            {error ? <p className="text-sm text-destructive">{error}</p> : null}
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? "注册中…" : "创建租户并登录"}
            </Button>
          </form>

          <p className="text-center text-xs text-muted-foreground">
            已有账号？{" "}
            <Link to="/login" className="text-primary hover:underline">
              返回登录
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
