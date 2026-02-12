"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useAuthStore } from "@/stores/useAuthStore";
import { api } from "@/lib/api";
import type { UserResponse, DashboardOverview } from "@/types/api";

export default function SettingsPage() {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const { clearTokens } = useAuthStore();

  useEffect(() => {
    Promise.all([
      api.get<UserResponse>("/auth/me").catch(() => null),
      api.get<DashboardOverview>("/dashboard/overview").catch(() => null),
    ])
      .then(([userData, overviewData]) => {
        setUser(userData);
        setOverview(overviewData);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-muted-foreground">Loading settings...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">
          Manage your account and data preferences
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Account Information</CardTitle>
          <CardDescription>Your account details</CardDescription>
        </CardHeader>
        <CardContent>
          {user ? (
            <dl className="space-y-3">
              <div className="flex justify-between py-1.5 border-b">
                <dt className="text-sm text-muted-foreground">Email</dt>
                <dd className="text-sm font-medium">{user.email}</dd>
              </div>
              <div className="flex justify-between py-1.5 border-b">
                <dt className="text-sm text-muted-foreground">Display Name</dt>
                <dd className="text-sm font-medium">{user.display_name || "Not set"}</dd>
              </div>
              <div className="flex justify-between py-1.5 border-b">
                <dt className="text-sm text-muted-foreground">Account Status</dt>
                <dd className="text-sm font-medium">
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                      user.is_active
                        ? "bg-emerald-100 text-emerald-800"
                        : "bg-red-100 text-red-800"
                    }`}
                  >
                    {user.is_active ? "Active" : "Inactive"}
                  </span>
                </dd>
              </div>
              <div className="flex justify-between py-1.5">
                <dt className="text-sm text-muted-foreground">User ID</dt>
                <dd className="text-sm font-mono text-muted-foreground">{user.id}</dd>
              </div>
            </dl>
          ) : (
            <p className="text-sm text-muted-foreground">Unable to load account information.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Data Management</CardTitle>
          <CardDescription>Overview of your stored health data</CardDescription>
        </CardHeader>
        <CardContent>
          {overview ? (
            <dl className="space-y-3">
              <div className="flex justify-between py-1.5 border-b">
                <dt className="text-sm text-muted-foreground">Total Records</dt>
                <dd className="text-sm font-medium">{overview.total_records}</dd>
              </div>
              <div className="flex justify-between py-1.5 border-b">
                <dt className="text-sm text-muted-foreground">Total Patients</dt>
                <dd className="text-sm font-medium">{overview.total_patients}</dd>
              </div>
              <div className="flex justify-between py-1.5 border-b">
                <dt className="text-sm text-muted-foreground">Total Uploads</dt>
                <dd className="text-sm font-medium">{overview.total_uploads}</dd>
              </div>
              <div className="flex justify-between py-1.5">
                <dt className="text-sm text-muted-foreground">Date Range</dt>
                <dd className="text-sm font-medium">
                  {overview.date_range_start && overview.date_range_end
                    ? `${new Date(overview.date_range_start).toLocaleDateString()} - ${new Date(overview.date_range_end).toLocaleDateString()}`
                    : "No data"}
                </dd>
              </div>
            </dl>
          ) : (
            <p className="text-sm text-muted-foreground">No data summary available.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Session</CardTitle>
          <CardDescription>Manage your current session</CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            variant="destructive"
            onClick={() => {
              clearTokens();
              window.location.href = "/login";
            }}
          >
            Sign Out
          </Button>
        </CardContent>
      </Card>

      <Alert>
        <AlertTitle>Data Privacy</AlertTitle>
        <AlertDescription>
          All your health data is stored locally and encrypted at rest. No data is transmitted to
          external services. AI summary prompts are constructed locally with de-identified data
          and are never sent automatically -- you control when and where to use them.
        </AlertDescription>
      </Alert>
    </div>
  );
}
