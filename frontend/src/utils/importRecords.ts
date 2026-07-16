export type ImportRecord = {
  id: string;
  dataType: string;
  dataTypeLabel: string;
  source: '人工上传';
  createdAt: string;
  importedRows: number;
  failedRows: number;
  duplicateRows: number;
};

function storageKey(projectId: string) {
  return `project-import-records:${projectId}`;
}

export function loadImportRecords(projectId: string): ImportRecord[] {
  try {
    const value = JSON.parse(localStorage.getItem(storageKey(projectId)) || '[]');
    return Array.isArray(value) ? value : [];
  } catch {
    localStorage.removeItem(storageKey(projectId));
    return [];
  }
}

export function saveImportRecord(projectId: string, record: Omit<ImportRecord, 'id' | 'createdAt' | 'source'>) {
  const next: ImportRecord = {
    ...record,
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    source: '人工上传',
    createdAt: new Date().toISOString(),
  };
  const records = [next, ...loadImportRecords(projectId)].slice(0, 20);
  localStorage.setItem(storageKey(projectId), JSON.stringify(records));
  return records;
}
