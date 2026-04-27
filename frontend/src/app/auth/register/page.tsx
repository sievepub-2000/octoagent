"use client";

import { CheckCircle2, KeyRound, Mail, MonitorCheck, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  deviceLogin,
  login,
  startDeviceVerification,
  startRegistration,
  verifyDevice,
  verifyRegistration,
  type AuthChallengeResponse,
} from "@/core/auth/api";
import { AUTH_STORAGE_KEYS, getDeviceFingerprint, saveAuthSession } from "@/core/auth/device";

const CODE_LENGTH = 8;

function formatRemaining(seconds: number) {
  const bounded = Math.max(0, seconds);
  const minutes = Math.floor(bounded / 60).toString().padStart(2, "0");
  const remainder = (bounded % 60).toString().padStart(2, "0");
  return `${minutes}:${remainder}`;
}

export default function AuthRegisterPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [code, setCode] = useState("");
  const [challenge, setChallenge] = useState<AuthChallengeResponse | null>(null);
  const [challengePurpose, setChallengePurpose] = useState<"registration" | "device" | null>(null);
  const [remaining, setRemaining] = useState(0);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    const savedUsername = localStorage.getItem(AUTH_STORAGE_KEYS.username);
    if (savedUsername) {
      setUsername(savedUsername);
      void attemptDeviceLogin(savedUsername, false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!challenge) {
      setRemaining(0);
      return;
    }
    const tick = () => setRemaining(Math.max(0, challenge.expires_at - Math.floor(Date.now() / 1000)));
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [challenge]);

  const canVerify = useMemo(() => Boolean(challenge && code.trim().length === CODE_LENGTH && remaining > 0), [challenge, code, remaining]);

  async function complete(session: Parameters<typeof saveAuthSession>[0]) {
    saveAuthSession(session);
    setStatus("认证成功，正在进入工作区");
    router.replace("/workspace/chats/new");
  }

  async function attemptDeviceLogin(name = username, showMissingDevice = true) {
    const normalized = name.trim();
    if (!normalized) {
      setError("请输入用户名");
      return;
    }
    setIsSubmitting(true);
    setError("");
    try {
      const device_fingerprint = await getDeviceFingerprint();
      const session = await deviceLogin({ username: normalized, device_fingerprint });
      await complete(session);
    } catch (err) {
      if (showMissingDevice) {
        setError(err instanceof Error ? err.message : "此终端需要邮箱验证");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setError("");
    setStatus("");
    try {
      const device_fingerprint = await getDeviceFingerprint();
      const session = await login({ username: username.trim(), password, device_fingerprint });
      await complete(session);
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleRegisterStart(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setError("");
    setStatus("");
    try {
      const response = await startRegistration({
        username: username.trim(),
        password,
        email: email.trim(),
        display_name: displayName.trim(),
      });
      setChallenge(response);
      setChallengePurpose("registration");
      setCode("");
      setStatus(response.delivery === "smtp" ? "验证码已发送到邮箱" : "验证码已写入服务端日志");
    } catch (err) {
      setError(err instanceof Error ? err.message : "注册请求失败");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDeviceVerifyStart() {
    setIsSubmitting(true);
    setError("");
    setStatus("");
    try {
      const response = await startDeviceVerification({ username: username.trim() });
      setChallenge(response);
      setChallengePurpose("device");
      setCode("");
      setStatus(response.delivery === "smtp" ? "验证码已发送到邮箱" : "验证码已写入服务端日志");
    } catch (err) {
      setError(err instanceof Error ? err.message : "终端验证请求失败");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleVerify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!challenge || !challengePurpose) return;
    setIsSubmitting(true);
    setError("");
    try {
      const device_fingerprint = await getDeviceFingerprint();
      const payload = { challenge_id: challenge.challenge_id, code: code.trim(), device_fingerprint };
      const session = challengePurpose === "registration" ? await verifyRegistration(payload) : await verifyDevice(payload);
      await complete(session);
    } catch (err) {
      setError(err instanceof Error ? err.message : "验证码校验失败");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen bg-background text-foreground">
      <section className="mx-auto flex min-h-screen w-full max-w-5xl items-center px-4 py-8 sm:px-6">
        <div className="grid w-full gap-8 md:grid-cols-[0.95fr_1.05fr] md:items-center">
          <div className="space-y-5">
            <div className="flex items-center gap-3">
              <div className="flex size-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <ShieldCheck className="size-5" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">OctoAgent Access</p>
                <h1 className="text-3xl font-semibold tracking-normal">账户与终端认证</h1>
              </div>
            </div>
            <div className="grid gap-3 text-sm text-muted-foreground">
              <div className="flex items-center gap-3"><Mail className="size-4 text-primary" />邮箱 8 位验证码，10 分钟有效</div>
              <div className="flex items-center gap-3"><KeyRound className="size-4 text-primary" />首次使用用户名和密码登录</div>
              <div className="flex items-center gap-3"><MonitorCheck className="size-4 text-primary" />后续使用已信任终端指纹进入</div>
            </div>
          </div>

          <div className="rounded-lg border bg-card p-5 shadow-sm sm:p-6">
            <Tabs value={mode} onValueChange={(value) => setMode(value as "login" | "register")} className="gap-5">
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="login">登录</TabsTrigger>
                <TabsTrigger value="register">注册</TabsTrigger>
              </TabsList>

              <TabsContent value="login" className="space-y-4">
                <form className="space-y-3" onSubmit={handleLogin}>
                  <Input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="用户名" autoComplete="username" required />
                  <Input value={password} onChange={(event) => setPassword(event.target.value)} placeholder="密码" type="password" autoComplete="current-password" required />
                  <div className="flex flex-col gap-2 sm:flex-row">
                    <Button type="submit" className="flex-1" disabled={isSubmitting}>{isSubmitting ? "处理中" : "用户名密码登录"}</Button>
                    <Button type="button" variant="outline" className="flex-1" disabled={isSubmitting} onClick={() => attemptDeviceLogin()}>终端登录</Button>
                  </div>
                </form>
                <Button type="button" variant="ghost" className="w-full" disabled={isSubmitting || !username.trim()} onClick={handleDeviceVerifyStart}>更换终端，邮箱验证</Button>
              </TabsContent>

              <TabsContent value="register" className="space-y-4">
                <form className="space-y-3" onSubmit={handleRegisterStart}>
                  <Input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="用户名" autoComplete="username" minLength={3} required />
                  <Input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="邮箱" type="email" autoComplete="email" required />
                  <Input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="显示名（可选）" autoComplete="name" />
                  <Input value={password} onChange={(event) => setPassword(event.target.value)} placeholder="密码" type="password" autoComplete="new-password" minLength={8} required />
                  <Button type="submit" className="w-full" disabled={isSubmitting}>{isSubmitting ? "发送中" : "发送验证码"}</Button>
                </form>
              </TabsContent>
            </Tabs>

            {challenge ? (
              <form className="mt-5 space-y-3 border-t pt-5" onSubmit={handleVerify}>
                <div className="flex items-center justify-between gap-3 text-sm">
                  <span className="font-medium">输入 8 位验证码</span>
                  <span className="tabular-nums text-muted-foreground">{formatRemaining(remaining)}</span>
                </div>
                <Input value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, CODE_LENGTH))} inputMode="numeric" placeholder="验证码" maxLength={CODE_LENGTH} required />
                {challenge.dev_code ? <p className="text-xs text-muted-foreground">开发验证码：{challenge.dev_code}</p> : null}
                <Button type="submit" className="w-full" disabled={!canVerify || isSubmitting}>{isSubmitting ? "校验中" : "确认并进入"}</Button>
              </form>
            ) : null}

            {status ? <p className="mt-4 flex items-center gap-2 text-sm text-primary"><CheckCircle2 className="size-4" />{status}</p> : null}
            {error ? <p className="mt-4 text-sm text-destructive">{error}</p> : null}
          </div>
        </div>
      </section>
    </main>
  );
}
