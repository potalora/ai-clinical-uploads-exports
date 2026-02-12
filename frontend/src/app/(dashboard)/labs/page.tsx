"use client";

import { useEffect, useState } from "react";
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
import type { LabItem } from "@/types/api";

function interpretationStyle(interpretation: string): string {
  const code = interpretation?.toUpperCase();
  if (code === "H" || code === "HH") return "text-red-600 font-medium";
  if (code === "L" || code === "LL") return "text-blue-600 font-medium";
  if (code === "A" || code === "AA") return "text-amber-600 font-medium";
  return "text-muted-foreground";
}

function interpretationLabel(interpretation: string): string {
  const code = interpretation?.toUpperCase();
  if (code === "H") return "High";
  if (code === "HH") return "Critical High";
  if (code === "L") return "Low";
  if (code === "LL") return "Critical Low";
  if (code === "A") return "Abnormal";
  if (code === "AA") return "Critical Abnormal";
  if (code === "N") return "Normal";
  return interpretation || "--";
}

export default function LabsPage() {
  const [labs, setLabs] = useState<LabItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<{ items: LabItem[] }>("/dashboard/labs")
      .then((data) => setLabs(data.items || []))
      .catch(() => setLabs([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-muted-foreground">Loading lab results...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Lab Results</h1>
        <p className="text-muted-foreground">
          View lab results with reference ranges and interpretation flags
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Lab Results</CardTitle>
          <CardDescription>{labs.length} results found</CardDescription>
        </CardHeader>
        <CardContent>
          {labs.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-muted-foreground">No lab results found.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Test</TableHead>
                  <TableHead>Value</TableHead>
                  <TableHead>Reference Range</TableHead>
                  <TableHead>Interpretation</TableHead>
                  <TableHead>Date</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {labs.map((lab) => (
                  <TableRow key={lab.id}>
                    <TableCell>
                      <div>
                        <p className="font-medium text-sm">{lab.display_text}</p>
                        {lab.code_display && lab.code_display !== lab.display_text && (
                          <p className="text-xs text-muted-foreground">{lab.code_display}</p>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="font-mono text-sm">
                        {lab.value !== null && lab.value !== undefined ? String(lab.value) : "--"}
                        {lab.unit && (
                          <span className="text-muted-foreground ml-1">{lab.unit}</span>
                        )}
                      </span>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {lab.reference_low !== null && lab.reference_high !== null
                        ? `${lab.reference_low} - ${lab.reference_high}`
                        : lab.reference_low !== null
                        ? `>= ${lab.reference_low}`
                        : lab.reference_high !== null
                        ? `<= ${lab.reference_high}`
                        : "--"}
                    </TableCell>
                    <TableCell>
                      <span className={`text-sm ${interpretationStyle(lab.interpretation)}`}>
                        {interpretationLabel(lab.interpretation)}
                      </span>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {lab.effective_date
                        ? new Date(lab.effective_date).toLocaleDateString()
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
