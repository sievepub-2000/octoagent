"use client";

import { CheckCircle2, KeyRound, Mail, MonitorCheck, ShieldCheck } from "lucide-react";
import { useI18n } from "@/core/i18n/hooks";
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
  const { t } = useI18n();
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
    setStatus(t.register.authSuccess);
    router.replace("/workspace/chats/new");
  }

  async function attemptDeviceLogin(name = username, showMissingDevice = true) {
    const normalized = name.trim();
    if (!normalized) {
      setError(t.register.enterUsername);
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
        setError(err instanceof Error ? err.message : t.register.needEmailVerify);
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
      setError(err instanceof Error ? err.message : t.register.loginFailed);
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
      setStatus(response.delivery === "smtp" ? t.register.codeSentEmail : t.register.codeWrittenLog);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.register.registerFailed);
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
      setStatus(response.delivery === "smtp" ? t.register.codeSentEmail : t.register.codeWrittenLog);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.register.deviceVerifyFailed);
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
      setError(err instanceof Error ? err.message : t.register.codeCheckFailed);
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
                <h1 className="text-3xl font-semibold tracking-normal">{t.register.title}</h1>
              </div>
            </div>
            <div className="grid gap-3 text-sm text-muted-foreground">
              <div className="flex items-center gap-3"><Mail className="size-4 text-primary" />{t.register.subtitleMail}</div>
              <div className="flex items-center gap-3"><KeyRound className="size-4 text-primary" />{t.register.subtitleFirst}</div>
              <div className="flex items-center gap-3"><MonitorCheck className="size-4 text-primary" />{t.register.subtitleTrust}</div>
            </div>
          </div>

          <div className="rounded-lg border bg-card p-5 shadow-sm sm:p-6">
            <Tabs value={mode} onValueChange={(value) => setMode(value as "login" | "register")} className="gap-5">
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="login">{t.register.tabLogin}</TabsTrigger>
                <TabsTrigger value="register">{t.register.tabRegister}</TabsTrigger>
              </TabsList>

              <TabsContent value="login" className="space-y-4">
                <form className="space-y-3" onSubmit={handleLogin}>
                  <Input value={username} onChange={(event) => setUsername(event.target.value)} placeholder={t.register.username} autoComplete="username" required />
                  <Input value={password} onChange={(event) => setPassword(event.target.value)} placeholder={t.register.password} type="password" autoComplete="current-password" required />
                  <div className="flex flex-col gap-2 sm:flex-row">
                    <Button type="submit" className="flex-1" disabled={isSubmitting}>{isSubmitting ? t.register.processing : t.register.userPassLogin}</Button>
                    <Button type="button" variant="outline" className="flex-1" disabled={isSubmitting} onClick={() => attemptDeviceLogin()}>{t.register.terminalLogin}</Button>
                  </div>
                </form>
                <Button type="button" variant="ghost" className="w-full" disabled={isSubmitting || !username.trim()} onClick={handleDeviceVerifyStart}>{t.register.switchTerminal}</Button>
              </TabsContent>

              <TabsContent value="register" className="space-y-4">
                <form className="space-y-3" onSubmit={handleRegisterStart}>
                  <Input value={username} onChange={(event) => setUsername(event.target.value)} placeholder={t.register.username} autoComplete="username" minLength={3} required />
                  <Input value={email} onChange={(event) => setEmail(event.target.value)} placeholder={t.register.email} type="email" autoComplete="email" required />
                  <Input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder={t.register.displayName} autoComplete="name" />
                  <Input value={password} onChange={(event) => setPassword(event.target.value)} placeholder={t.register.password} type="password" autoComplete="new-password" minLength={8} required />
                  <Button type="submit" className="w-full" disabled={isSubmitting}>{isSubmitting ? t.register.sending : t.register.sendCode}</Button>
                </form>
              </TabsContent>
            </Tabs>

            {challenge ? (
              <form className="mt-5 space-y-3 border-t pt-5" onSubmit={handleVerify}>
                <div className="flex items-center justify-between gap-3 text-sm">
                  <span className="font-medium">{t.register.enter8Digit}</span>
                  <span className="tabular-nums text-muted-foreground">{formatRemaining(remaining)}</span>
                </div>
                <Input value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, CODE_LENGTH))} inputMode="numeric" placeholder={t.register.verifyCode} maxLength={CODE_LENGTH} required />
                {challenge.dev_code ? <p className="text-xs text-muted-foreground">{t.register.devCode}{challenge.dev_code}</p> : null}
                <Button type="submit" className="w-full" disabled={!canVerify || isSubmitting}>{isSubmitting ? t.register.verifying : t.register.verifyAndEnter}</Button>
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
