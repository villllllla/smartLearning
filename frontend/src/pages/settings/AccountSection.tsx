import { FormEvent, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { KeyRound, Loader2 } from "lucide-react";

import { authApi } from "@/api/auth";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { useAuth } from "@/lib/AuthContext";
import { TimezoneSection } from "./TimezoneSection";

export function AccountSection() {
  const { user, authEnabled } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const changePassword = useMutation({
    mutationFn: () =>
      authApi.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    onSuccess: () => {
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      toast.success("密码已更新");
    },
    onError: (e: Error) => toast.error(e instanceof ApiError ? e.message : "修改失败"),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      toast.error("两次输入的新密码不一致");
      return;
    }
    changePassword.mutate();
  }

  if (!authEnabled) {
    return (
      <div className="space-y-6">
        <TimezoneSection />
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">
            当前环境已关闭登录鉴权，无需修改密码。
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!user || user.id === 0) {
    return (
      <div className="space-y-6">
        <TimezoneSection />
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">
            请使用账号密码登录后再修改密码（服务令牌无法修改密码）。
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <TimezoneSection />
      <Card>
        <CardContent className="space-y-3 p-6">
          <div className="flex items-center gap-2 text-base font-semibold">
            <KeyRound className="h-4 w-4 text-primary" />
            账号信息
          </div>
          <dl className="grid gap-2 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-muted-foreground">邮箱</dt>
              <dd className="font-medium">{user.email}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">显示名</dt>
              <dd className="font-medium">{user.display_name}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">租户</dt>
              <dd className="font-medium">{user.tenant_name}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">角色</dt>
              <dd className="font-medium">{user.role}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-4 p-6">
          <div>
            <div className="text-base font-semibold">修改密码</div>
            <p className="mt-1 text-sm text-muted-foreground">
              修改成功后仍保持当前登录状态，下次登录请使用新密码。
            </p>
          </div>

          <form className="max-w-md space-y-4" onSubmit={onSubmit}>
            <div className="space-y-2">
              <Label htmlFor="current-password">当前密码</Label>
              <Input
                id="current-password"
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-password">新密码</Label>
              <Input
                id="new-password"
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                minLength={8}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirm-password">确认新密码</Label>
              <Input
                id="confirm-password"
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                minLength={8}
                required
              />
            </div>
            <Button type="submit" disabled={changePassword.isPending}>
              {changePassword.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : null}
              保存新密码
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
