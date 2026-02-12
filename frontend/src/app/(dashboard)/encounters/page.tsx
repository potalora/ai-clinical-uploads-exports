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

export default function EncountersPage() {
  const [data, setData] = useState<RecordListResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<RecordListResponse>("/records?record_type=encounter&page_size=100")
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-muted-foreground">Loading encounters...</p>
      </div>
    );
  }

  const records = data?.items || [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Encounters</h1>
        <p className="text-muted-foreground">
          View visits, appointments, and clinical encounters
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Encounter Records</CardTitle>
          <CardDescription>{records.length} encounters found</CardDescription>
        </CardHeader>
        <CardContent>
          {records.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-muted-foreground">No encounter records found.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Encounter</TableHead>
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
                          record.status === "finished"
                            ? "bg-emerald-100 text-emerald-800"
                            : record.status === "in-progress"
                            ? "bg-blue-100 text-blue-800"
                            : record.status === "cancelled"
                            ? "bg-red-100 text-red-800"
                            : record.status === "planned"
                            ? "bg-amber-100 text-amber-800"
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
