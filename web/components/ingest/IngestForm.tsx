"use client";

import { FileDropZone } from "@/components/ingest/FileDropZone";
import { FormFieldLabel } from "@/components/ingest/FormFieldLabel";
import { IngestPreflightBanner } from "@/components/ingest/IngestPreflightBanner";
import { JobPositionPicker } from "@/components/ingest/JobPositionPicker";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { MachineSelector } from "@/components/ui/MachineSelector";
import { useDocumentTypes } from "@/hooks/useDocumentTypes";
import { useFactoriesQuery } from "@/hooks/useFactoriesQuery";
import { useIngestPreflight } from "@/hooks/useIngestPreflight";
import { useMachinesInfinite } from "@/hooks/useMachinesQuery";
import { api, type IngestFileResponse } from "@/lib/api";
import { canUploadDocuments } from "@/lib/auth";
import {
  documentTypeLabel,
  documentTypeRecommendsMachine,
  documentTypeRequiresMachine,
  documentTypeShowsMachineField,
  type DocumentCategoryId,
} from "@/lib/document-categories";
import { parseApiError } from "@/lib/errors";
import {
  guessDocumentTypeFromFilename,
  resolveDefaultDocumentType,
} from "@/lib/ingest-defaults";
import { isFileAcceptedForDocumentType } from "@/lib/ingest-upload";
import { useUiStore } from "@/stores/uiStore";
import { useQueryClient } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type IngestFormProps = {
  onSuccess?: (result: IngestFileResponse) => void;
  embedded?: boolean;
  defaultMachineId?: string;
  filterDocumentTypes?: string[];
  /** Hub category — sets default type and filtered list when filterDocumentTypes omitted. */
  documentCategory?: DocumentCategoryId;
  defaultDocumentType?: string;
};

const fieldClass =
  "mt-1 w-full h-9 rounded-md border border-gemini-border dark:border-gemini-dark-border bg-gemini-bg/50 dark:bg-gemini-dark-bg/50 px-2 text-sm outline-none focus:border-gemini-blue dark:focus:border-gemini-dark-blue";

export function IngestForm({
  onSuccess,
  embedded = false,
  defaultMachineId,
  filterDocumentTypes,
  documentCategory,
  defaultDocumentType,
}: IngestFormProps) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const selectedFactoryId = useUiStore((s) => s.selectedFactoryId);
  const selectedMachineId = useUiStore((s) => s.selectedMachineId);
  const { documentTypes: allDocumentTypes, isLoading: typesLoading } = useDocumentTypes();
  const documentTypes = filterDocumentTypes
    ? allDocumentTypes.filter((t) => filterDocumentTypes.includes(t))
    : allDocumentTypes;
  const { data: factories = [] } = useFactoriesQuery();
  const { result: preflight, loading: preflightLoading, error: preflightError, run: runPreflight, reset: resetPreflight } =
    useIngestPreflight();

  const factoryOptions = useMemo(
    () => factories.map((f) => f.factory_id).sort(),
    [factories]
  );

  const initialFactory =
    selectedFactoryId ?? (factoryOptions.length === 1 ? factoryOptions[0] : "");

  const [file, setFile] = useState<File | null>(null);
  const [documentType, setDocumentType] = useState("");
  const [factoryId, setFactoryId] = useState(initialFactory);
  const [machineId, setMachineId] = useState(defaultMachineId ?? selectedMachineId ?? "");
  const [machineSearch, setMachineSearch] = useState("");
  const [visiblePositionIds, setVisiblePositionIds] = useState<string[]>([]);
  const [title, setTitle] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<IngestFileResponse | null>(null);
  const [suggestedType, setSuggestedType] = useState<string | null>(null);
  const [userOverrodeType, setUserOverrodeType] = useState(false);
  const submitLockRef = useRef(false);
  const userPickedTypeRef = useRef(false);
  const defaultsAppliedRef = useRef(false);

  const showFactorySelect = factoryOptions.length > 1;
  const showMachineField =
    Boolean(defaultMachineId) || documentTypeShowsMachineField(documentType);
  const machineRequired = documentTypeRequiresMachine(documentType);
  const showMachineSuggestion =
    showMachineField && !machineRequired && !machineId && documentTypeRecommendsMachine(documentType);

  const resolvedFactoryId = factoryId || selectedFactoryId || factoryOptions[0] || "";

  const applySuggestedType = useCallback(
    (filename: string, preflightType?: string | null) => {
      if (userPickedTypeRef.current) return;
      const fromPreflight =
        preflightType && documentTypes.includes(preflightType) ? preflightType : null;
      const fromFilename = guessDocumentTypeFromFilename(filename, documentTypes);
      const next = fromPreflight ?? fromFilename;
      if (next && next !== documentType) {
        setDocumentType(next);
        setSuggestedType(next);
      } else if (fromPreflight) {
        setSuggestedType(fromPreflight);
      } else if (fromFilename) {
        setSuggestedType(fromFilename);
      }
    },
    [documentTypes, documentType]
  );

  useEffect(() => {
    if (!showMachineField && !defaultMachineId) {
      setMachineId("");
    }
  }, [showMachineField, defaultMachineId]);

  useEffect(() => {
    if (selectedFactoryId) setFactoryId(selectedFactoryId);
    else if (factoryOptions.length === 1) setFactoryId(factoryOptions[0]);
  }, [selectedFactoryId, factoryOptions]);

  useEffect(() => {
    if (defaultMachineId) setMachineId(defaultMachineId);
  }, [defaultMachineId]);

  useEffect(() => {
    if (defaultsAppliedRef.current || documentTypes.length === 0) return;
    const preferred =
      defaultDocumentType ??
      resolveDefaultDocumentType({
        category: documentCategory,
        defaultMachineId,
        availableTypes: documentTypes,
      });
    if (preferred && documentTypes.includes(preferred)) {
      setDocumentType(preferred);
    } else {
      setDocumentType(documentTypes[0]);
    }
    defaultsAppliedRef.current = true;
  }, [documentTypes, defaultDocumentType, documentCategory, defaultMachineId]);

  useEffect(() => {
    if (file && documentType && !isFileAcceptedForDocumentType(file, documentType)) {
      setFile(null);
      resetPreflight();
      setSuggestedType(null);
      setError("รูปแบบไฟล์ไม่ตรงกับประเภทเอกสาร — เลือกไฟล์ใหม่หรือเปลี่ยนประเภท");
    }
  }, [documentType, file, resetPreflight]);

  const triggerPreflight = useCallback(
    (nextFile: File, typeOverride?: string) => {
      if (!resolvedFactoryId) return;
      runPreflight({
        file: nextFile,
        factoryId: resolvedFactoryId,
        machineId: machineId || undefined,
        documentType: typeOverride ?? (userPickedTypeRef.current ? documentType : undefined),
      });
    },
    [resolvedFactoryId, machineId, documentType, runPreflight]
  );

  const handleFileChange = useCallback(
    (next: File | null) => {
      setFile(next);
      setResult(null);
      setError("");
      resetPreflight();
      setSuggestedType(null);
      userPickedTypeRef.current = false;
      setUserOverrodeType(false);

      if (!next) return;
      applySuggestedType(next.name);
      triggerPreflight(next);
    },
    [applySuggestedType, resetPreflight, triggerPreflight]
  );

  useEffect(() => {
    if (!file || !resolvedFactoryId) return;
    triggerPreflight(file);
  }, [documentType, machineId, resolvedFactoryId, file, triggerPreflight]);

  useEffect(() => {
    if (!preflight?.document_type || !file || userPickedTypeRef.current) return;
    applySuggestedType(file.name, preflight.document_type);
  }, [preflight?.document_type, file, applySuggestedType]);

  const {
    machines,
    isLoading: machinesLoading,
    hasMore: machinesHasMore,
    loadMore: loadMoreMachines,
  } = useMachinesInfinite(machineSearch, {
    enabled: Boolean(resolvedFactoryId) && showMachineField,
    factoryId: resolvedFactoryId || null,
  });

  const canUpload = useMemo(
    () => canUploadDocuments(factoryId || selectedFactoryId),
    [factoryId, selectedFactoryId]
  );

  const canSubmit =
    Boolean(file) &&
    !loading &&
    !preflightLoading &&
    (preflight?.accepted ?? false);

  if (!canUpload) {
    const readOnly = (
      <p className="text-sm text-gemini-muted dark:text-gemini-dark-muted">
        อัปโหลดเอกสารได้เฉพาะ Admin และ Operator
      </p>
    );
    return embedded ? readOnly : <Card>{readOnly}</Card>;
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (loading || submitLockRef.current) return;
    if (!file) {
      setError("กรุณาเลือกไฟล์");
      return;
    }
    const resolvedFactory = factoryId || selectedFactoryId || factoryOptions[0];
    if (!resolvedFactory) {
      setError("กรุณาเลือกโรงงาน");
      return;
    }
    if (machineRequired && !machineId) {
      setError("ประเภทเอกสารนี้ต้องเลือกเครื่องจักร");
      return;
    }
    if (!preflight?.accepted) {
      setError(
        preflight?.reasons?.[0] ??
          "ไฟล์ยังไม่ผ่านการตรวจสอบ — รอสักครู่หรือแก้ไขตามข้อความด้านบน"
      );
      return;
    }
    setError("");
    setResult(null);
    setLoading(true);
    submitLockRef.current = true;
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("factory_id", resolvedFactory);
      if (documentType) form.append("document_type", documentType);
      if (machineId) form.append("machine_id", machineId);
      if (title.trim()) form.append("title", title.trim());
      if (visiblePositionIds.length > 0) {
        form.append("visible_position_ids", JSON.stringify(visiblePositionIds));
      }

      const response = await api.ingestFile(form);
      setResult(response);
      queryClient.invalidateQueries({ queryKey: ["ingestJobs"] });
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      onSuccess?.(response);
      setFile(null);
      resetPreflight();
      setSuggestedType(null);
      userPickedTypeRef.current = false;
      setUserOverrodeType(false);
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setLoading(false);
      submitLockRef.current = false;
    }
  }

  const form = (
    <form onSubmit={onSubmit} className="space-y-4" data-testid="upload-form">
      <div className="grid gap-5 md:grid-cols-[minmax(0,220px)_1fr]">
        <FileDropZone
          file={file}
          onFileChange={handleFileChange}
          onValidationError={setError}
          disabled={loading}
          fillColumn
          documentType={documentType}
          acceptAnySupported
        />

        <div className="space-y-3 min-w-0">
          <p className="text-xs text-gemini-muted dark:text-gemini-dark-muted pb-0.5">
            ลากไฟล์มาวางเพื่อให้ระบบแนะนำประเภท · ช่องที่มีป้าย{" "}
            <span className="text-amber-800 dark:text-amber-300 font-medium">บังคับ</span> ต้องกรอกก่อนอัปโหลด
          </p>

          {file && (
            <IngestPreflightBanner
              result={preflight}
              loading={preflightLoading}
              error={preflightError}
              suggestedType={suggestedType}
              userOverrodeType={userOverrodeType}
            />
          )}

          <div className="block text-sm">
            <FormFieldLabel required htmlFor="ingest-document-type">
              ประเภทเอกสาร
            </FormFieldLabel>
            <select
              id="ingest-document-type"
              value={documentType}
              onChange={(e) => {
                userPickedTypeRef.current = true;
                setUserOverrodeType(true);
                setSuggestedType(null);
                setDocumentType(e.target.value);
              }}
              disabled={typesLoading || documentTypes.length === 0}
              className={fieldClass}
            >
              {documentTypes.length > 0 ? (
                documentTypes.map((t) => (
                  <option key={t} value={t}>
                    {documentTypeLabel(t)}
                  </option>
                ))
              ) : (
                <option value="">{typesLoading ? "กำลังโหลด…" : "—"}</option>
              )}
            </select>
          </div>

          {showFactorySelect ? (
            <div className="block text-sm">
              <FormFieldLabel required htmlFor="ingest-factory">
                โรงงาน
              </FormFieldLabel>
              <select
                id="ingest-factory"
                value={factoryId}
                onChange={(e) => {
                  setFactoryId(e.target.value);
                  setMachineId("");
                }}
                className={fieldClass}
              >
                {factoryOptions.length > 0 ? (
                  factoryOptions.map((id) => (
                    <option key={id} value={id}>
                      {id}
                    </option>
                  ))
                ) : (
                  <option value="">—</option>
                )}
              </select>
            </div>
          ) : (
            (factoryId || selectedFactoryId) && (
              <div className="rounded-lg border border-gemini-border/60 dark:border-gemini-dark-border/60 bg-gemini-bg/50 dark:bg-gemini-dark-bg/50 px-3 py-2 text-sm">
                <FormFieldLabel required>โรงงาน</FormFieldLabel>
                <p className="font-medium mt-1">{factoryId || selectedFactoryId}</p>
                <p className="text-xs text-gemini-muted dark:text-gemini-dark-muted mt-0.5">
                  ใช้โรงงานที่เลือกในเมนูด้านบน
                </p>
              </div>
            )
          )}

          {showMachineField && (
            <div className="min-w-0">
              <FormFieldLabel required={machineRequired}>ผูกกับเครื่องจักร</FormFieldLabel>
              <div className="mt-1">
                <MachineSelector
                  machines={machines}
                  value={machineId || null}
                  onChange={(id) => {
                    if (!defaultMachineId) setMachineId(id ?? "");
                  }}
                  isLoading={machinesLoading}
                  hasMore={machinesHasMore}
                  onLoadMore={() => loadMoreMachines()}
                  placeholder={defaultMachineId ? defaultMachineId : "เลือกเครื่องจักร…"}
                  serverSearch
                  searchQuery={machineSearch}
                  onSearchQueryChange={defaultMachineId ? undefined : setMachineSearch}
                  compact
                />
              </div>
              {!machineRequired && (
                <p className="mt-1 text-xs text-gemini-muted dark:text-gemini-dark-muted">
                  เว้นว่าง = เอกสารกลาง
                </p>
              )}
              {showMachineSuggestion && (
                <div className="mt-2 rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
                  เอกสารประเภทนี้มักเป็นของเครื่องใดเครื่องหนึ่ง ถ้าเป็นเอกสารเฉพาะเครื่อง แนะนำให้เลือกเครื่องก่อนอัปโหลด
                </div>
              )}
            </div>
          )}

          <div className="block text-sm">
            <FormFieldLabel htmlFor="ingest-title">ชื่อเอกสาร</FormFieldLabel>
            <input
              id="ingest-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="เว้นว่างได้"
              className={fieldClass}
            />
          </div>

          <JobPositionPicker
            selectedIds={visiblePositionIds}
            onChange={setVisiblePositionIds}
            disabled={loading}
          />
        </div>
      </div>

      {error && (
        <p className="text-xs text-red-600 dark:text-red-400" role="alert">
          {error}
        </p>
      )}

      {result && (
        <div className="rounded-lg border border-green-500/30 bg-green-500/10 p-3 text-sm space-y-2">
          <p>อัปโหลดสำเร็จ — อยู่ในคิวประมวลผล</p>
          <p className="font-mono text-xs text-gemini-muted">Job: {result.job_id}</p>
          <button
            type="button"
            onClick={() => {
              const el = document.getElementById("jobs");
              if (el) {
                el.scrollIntoView({ behavior: "smooth", block: "start" });
              } else {
                router.push("/upload#jobs");
              }
            }}
            className="text-xs text-gemini-blue dark:text-gemini-dark-blue hover:underline"
          >
            ดูสถานะงาน ↓
          </button>
        </div>
      )}

      <div className="flex flex-wrap gap-2 pt-1 border-t border-gemini-border/40 dark:border-gemini-dark-border/40">
        <Button
          type="submit"
          variant="primary"
          loading={loading}
          disabled={!canSubmit}
          leftIcon={<Upload className="h-4 w-4" />}
        >
          อัปโหลด
        </Button>
      </div>
    </form>
  );

  if (embedded) return form;

  return (
    <Card>
      <CardHeader>
        <CardTitle>อัปโหลดเอกสาร</CardTitle>
      </CardHeader>
      {form}
    </Card>
  );
}
