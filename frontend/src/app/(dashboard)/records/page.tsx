"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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

const TYPE_COLORS: Record<string, string> = {
  condition: "bg-amber-100 text-amber-800",
  observation: "bg-teal-100 text-teal-800",
  medication: "bg-violet-100 text-violet-800",
  encounter: "bg-emerald-100 text-emerald-800",
  immunization: "bg-blue-100 text-blue-800",
  procedure: "bg-rose-100 text-rose-800",
  document: "bg-slate-100 text-slate-800",
  diagnostic_report: "bg-cyan-100 text-cyan-800",
  allergy: "bg-red-100 text-red-800",
  imaging: "bg-purple-100 text-purple-800",
};

const RECORD_TYPES = [
  { value: "", label: "All Types" },
  { value: "condition", label: "Conditions" },
  { value: "observation", label: "Observations" },
  { value: "medication", label: "Medications" },
  { value: "encounter", label: "Encounters" },
  { value: "immunization", label: "Immunizations" },
  { value: "procedure", label: "Procedures" },
  { value: "document", label: "Documents" },
  { value: "imaging", label: "Imaging" },
  { value: "allergy", label: "Allergies" },
  { value: "diagnostic_report", label: "Diagnostic Reports" },
];

export default function RecordsPage() {
  const [data, setData] = useState<RecordListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [recordType, setRecordType] = useState("");
  const [searchInput, setSearchInput] = useState("");

  useEffect(() => {
    setLoading(true);
    let endpoint = `/records?page=${page}&page_size=20`;
    if (recordType) endpoint += `&record_type=${recordType}`;
    if (search) endpoint += `&search=${encodeURIComponent(search)}`;

    api
      .get<RecordListResponse>(endpoint)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [page, recordType, search]);

  const handleSearch = () => {
    setSearch(searchInput);
    setPage(1);
  };

  const handleTypeChange = (type: string) => {
    setRecordType(type);
    setPage(1);
  };

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Health Records</h1>
        <p className="text-muted-foreground">Browse, search, and filter all medical records</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Filter Records</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="flex flex-1 gap-2">
              <Input
                placeholder="Search records..."
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              />
              <Button onClick={handleSearch} variant="secondary">
                Search
              </Button>
            </div>
            <select
              className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
              value={recordType}
              onChange={(e) => handleTypeChange(e.target.value)}
            >
              {RECORD_TYPES.map((rt) => (
                <option key={rt.value} value={rt.value}>
                  {rt.label}
                </option>
              ))}
            </select>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          {loading ? (
            <div className="flex items-center justify-center h-32">
              <p className="text-muted-foreground">Loading records...</p>
            </div>
          ) : !data || data.items.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-muted-foreground">No records found.</p>
              {(search || recordType) && (
                <Button
                  variant="link"
                  onClick={() => {
                    setSearch("");
                    setSearchInput("");
                    setRecordType("");
                    setPage(1);
                  }}
                >
                  Clear filters
                </Button>
              )}
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Type</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead>Date</TableHead>
                    <TableHead>Source</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((record) => (
                    <TableRow key={record.id}>
                      <TableCell>
                        <span
                          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                            TYPE_COLORS[record.record_type] || "bg-gray-100 text-gray-800"
                          }`}
                        >
                          {record.record_type}
                        </span>
                      </TableCell>
                      <TableCell>
                        <Link
                          href={`/records/${record.id}`}
                          className="text-primary hover:underline"
                        >
                          {record.display_text}
                        </Link>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {record.effective_date
                          ? new Date(record.effective_date).toLocaleDateString()
                          : "No date"}
                      </TableCell>
                      <TableCell className="text-muted-foreground text-xs">
                        {record.source_format}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              <div className="flex items-center justify-between pt-4">
                <p className="text-sm text-muted-foreground">
                  Showing {(data.page - 1) * data.page_size + 1} -{" "}
                  {Math.min(data.page * data.page_size, data.total)} of {data.total}
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => setPage((p) => p - 1)}
                  >
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page >= totalPages}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    Next
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
