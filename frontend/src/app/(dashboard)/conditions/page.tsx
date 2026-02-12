"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import type { RecordListResponse } from "@/types/api";

export default function ConditionsPage() {
  const [data, setData] = useState<RecordListResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<RecordListResponse>("/records?record_type=condition&page_size=100")
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-muted-foreground">Loading conditions...</p>
      </div>
    );
  }

  const records = data?.items || [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Conditions</h1>
        <p className="text-muted-foreground">
          View diagnoses and medical conditions
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Condition Records</CardTitle>
          <CardDescription>{records.length} conditions found</CardDescription>
        </CardHeader>
        <CardContent>
          {records.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-muted-foreground">No condition records found.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Condition</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Date</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {records.map((record) => (
                  <TableRow key={record.id}>
                    <TableCell>
                      <Link
                        href={`/records/${record.id}`}
                        className="text-sm font-medium text-primary hover:underline"
                      >
                        {record.display_text}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                          record.status === "active"
                            ? "bg-amber-100 text-amber-800"
                            : record.status === "resolved"
                            ? "bg-emerald-100 text-emerald-800"
                            : record.status === "inactive"
                            ? "bg-gray-100 text-gray-800"
                            : "bg-gray-100 text-gray-800"
                        }`}
                      >
                        {record.status || "unknown"}
                      </span>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {record.effective_date
                        ? new Date(record.effective_date).toLocaleDateString()
                        : "No date"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
