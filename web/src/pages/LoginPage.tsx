import { type FormEvent, useState } from "react";

import { useDemoLogin, useLogin, useSignInOptions } from "@/auth/session";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function LoginPage() {
  const login = useLogin();
  const demo = useDemoLogin();
  const options = useSignInOptions();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    login.mutate({ email, password });
  }

  return (
    <main className="flex min-h-svh items-center justify-center bg-muted p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>job-seeker</CardTitle>
          <CardDescription>Sign in to your account.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-4" onSubmit={submit}>
            <div className="flex flex-col gap-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>
            {login.isError && (
              <p role="alert" className="text-sm text-destructive">
                {login.error.message}
              </p>
            )}
            <Button type="submit" disabled={login.isPending}>
              {login.isPending ? "Signing in…" : "Sign in"}
            </Button>
          </form>
          {options.data?.demo_login && (
            <div className="mt-4 flex flex-col gap-2 border-t pt-4">
              <p className="text-sm text-muted-foreground">
                Or look around a made-up job search, read only.
              </p>
              <Button variant="outline" disabled={demo.isPending} onClick={() => demo.mutate()}>
                Try the demo
              </Button>
              {demo.isError && (
                <p role="alert" className="text-sm text-destructive">
                  {demo.error.message}
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
