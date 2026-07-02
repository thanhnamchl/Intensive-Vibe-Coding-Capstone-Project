import React, { useState, useEffect, useRef } from 'react';
import type { DataStatus } from './types';
import { TRANSLATIONS } from './translations';
import { API_BASE, MAX_UPLOAD_BYTES } from './config';

type GateView = 'scanning' | 'upload';

interface UploadGateProps {
    lang: 'vi' | 'en';
    setLang: React.Dispatch<React.SetStateAction<'vi' | 'en'>>;
    onReady: () => void;
    forceUpload?: boolean;
}

export function UploadGate({ lang, setLang, onReady, forceUpload = false }: UploadGateProps) {
    const t = TRANSLATIONS[lang];
    const [view, setView] = useState<GateView>('scanning');
    const [requiredColumns, setRequiredColumns] = useState<string[]>([]);
    const [dragActive, setDragActive] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [errors, setErrors] = useState<string[]>([]);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);
    const [fileName, setFileName] = useState<string | null>(null);
    const [downloadingSample, setDownloadingSample] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const checkStatus = async () => {
        if (forceUpload) {
            setView('upload');
            try {
                const res = await fetch(`${API_BASE}/data-status`);
                const data: DataStatus = await res.json();
                setRequiredColumns(data.required_columns || []);
            } catch (e) {
                console.error('Error fetching required columns', e);
            }
            return;
        }

        setView('scanning');
        try {
            const res = await fetch(`${API_BASE}/data-status`);
            const data: DataStatus = await res.json();
            setRequiredColumns(data.required_columns || []);
            if (data.data_loaded) {
                onReady();
                return;
            }
            setView('upload');
        } catch (e) {
            console.error('Error checking data status', e);
            setErrorMessage(t.serverConnectionError);
            setView('upload');
        }
    };

    useEffect(() => {
        checkStatus();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [forceUpload]);

    const downloadSampleCsv = async () => {
        setDownloadingSample(true);
        try {
            const res = await fetch(`${API_BASE}/sample-csv`);
            if (!res.ok) throw new Error('download failed');
            const blob = await res.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'star_farm_template.csv';
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
        } catch (e) {
            console.error('Error downloading sample CSV', e);
            setErrorMessage(lang === 'vi' ? 'Không tải được file mẫu. Vui lòng thử lại.' : 'Failed to download sample file. Please try again.');
        } finally {
            setDownloadingSample(false);
        }
    };

    const uploadFile = async (file: File) => {
        setErrors([]);
        setErrorMessage(null);

        if (!file.name.toLowerCase().endsWith('.csv')) {
            setErrorMessage(t.onlyCsv);
            return;
        }
        if (file.size > MAX_UPLOAD_BYTES) {
            setErrorMessage(
                `${t.fileTooLarge} (${(file.size / 1024 / 1024).toFixed(1)}MB). ${t.maxLimit}: ${(MAX_UPLOAD_BYTES / 1024 / 1024).toFixed(0)}MB.`
            );
            return;
        }

        setFileName(file.name);
        setUploading(true);
        try {
            const formData = new FormData();
            formData.append('file', file);

            const res = await fetch(`${API_BASE}/upload`, {
                method: 'POST',
                body: formData,
            });
            const data = await res.json();

            if (!res.ok) {
                const detail = data.detail;
                setErrorMessage((typeof detail === 'string' ? detail : detail?.message) || t.uploadFailed);
                setErrors(detail?.errors || []);
                if (detail?.required_columns) setRequiredColumns(detail.required_columns);
                return;
            }

            onReady();
        } catch (e) {
            console.error('Error uploading CSV', e);
            setErrorMessage(t.connectionError);
        } finally {
            setUploading(false);
        }
    };

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        setDragActive(false);
        const file = e.dataTransfer.files?.[0];
        if (file) uploadFile(file);
    };

    const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) uploadFile(file);
        e.target.value = '';
    };

    if (view === 'scanning') {
        return (
            <div className="upload-gate-container">
                <div style={{ position: 'absolute', top: '1rem', right: '1rem', zIndex: 10 }}>
                    <div className="lang-toggle-container">
                        <button
                            type="button"
                            className={`lang-toggle-btn ${lang === 'vi' ? 'active' : ''}`}
                            onClick={() => setLang('vi')}
                        >
                            VI
                        </button>
                        <button
                            type="button"
                            className={`lang-toggle-btn ${lang === 'en' ? 'active' : ''}`}
                            onClick={() => setLang('en')}
                        >
                            EN
                        </button>
                    </div>
                </div>
                <div className="upload-gate-card upload-gate-scan">
                    <div className="upload-scan-orb">
                        <span className="spinner-text">(o)</span>
                    </div>
                    <p className="upload-scan-text">{t.checkingStatus}</p>
                    <p className="upload-scan-subtext">{t.checkingStatusSub}</p>
                </div>
            </div>
        );
    }

    return (
        <div className="upload-gate-container">
            <div style={{ position: 'absolute', top: '1rem', right: '1rem', zIndex: 10 }}>
                <div className="lang-toggle-container">
                    <button
                        type="button"
                        className={`lang-toggle-btn ${lang === 'vi' ? 'active' : ''}`}
                        onClick={() => setLang('vi')}
                    >
                        VI
                    </button>
                    <button
                        type="button"
                        className={`lang-toggle-btn ${lang === 'en' ? 'active' : ''}`}
                        onClick={() => setLang('en')}
                    >
                        EN
                    </button>
                </div>
            </div>
            <div className="upload-gate-card">
                <div className="upload-gate-icon">[-]</div>

                <div className="header-title upload-gate-header">
                    <h1>{t.title}</h1>
                    <p>{t.noDataSimulationTitle}</p>
                </div>

                {/* Step 1 */}
                <div className="upload-step">
                    <div className="upload-step-icon">1</div>
                    <div className="upload-step-body">
                        <h3>{t.downloadTemplateTitle}</h3>
                        <p>{t.downloadTemplateDesc}</p>
                        <button
                            type="button"
                            className="btn btn-outline upload-sample-btn"
                            onClick={downloadSampleCsv}
                            disabled={downloadingSample}
                        >
                            {downloadingSample ? <span className="spinner-text">(o)</span> : '[-]'}
                            &nbsp;{t.downloadTemplateBtn}
                        </button>
                    </div>
                </div>

                {/* Step 2 */}
                <div className="upload-step">
                    <div className="upload-step-icon">2</div>
                    <div className="upload-step-body" style={{ width: '100%' }}>
                        <h3>{t.uploadYourFile}</h3>
                        <div
                            className={`upload-dropzone ${dragActive ? 'active' : ''} ${uploading ? 'busy' : ''}`}
                            onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
                            onDragLeave={() => setDragActive(false)}
                            onDrop={handleDrop}
                            onClick={() => !uploading && fileInputRef.current?.click()}
                        >
                            <input
                                ref={fileInputRef}
                                type="file"
                                accept=".csv"
                                style={{ display: 'none' }}
                                onChange={handleFileInput}
                                disabled={uploading}
                            />
                            {uploading ? (
                                <>
                                    <span className="spinner-text" style={{ fontSize: '1.8rem' }}>(o)</span>
                                    <p className="upload-dropzone-title">{t.processing.replace('{file}', fileName || '')}</p>
                                    <p className="upload-dropzone-subtitle">{t.verifyingTemplate}</p>
                                </>
                            ) : (
                                <>
                                    <div style={{ fontSize: '1.8rem' }}>[-]</div>
                                    <p className="upload-dropzone-title">{t.dragDropText}</p>
                                    <p className="upload-dropzone-subtitle">
                                        {t.maxLimit} {(MAX_UPLOAD_BYTES / 1024 / 1024).toFixed(0)}MB &middot; .csv
                                    </p>
                                </>
                            )}
                        </div>
                    </div>
                </div>

                {errorMessage && (
                    <div className="upload-error-box">
                        <div className="upload-error-title">
                            [!] {errorMessage}
                        </div>
                        {errors.length > 0 && (
                            <ul className="upload-error-list">
                                {errors.map((err, i) => <li key={i}>{err}</li>)}
                            </ul>
                        )}
                    </div>
                )}

                {requiredColumns.length > 0 && (
                    <details className="upload-columns-details">
                        <summary>
                            [-] {t.viewRequiredCols.replace('{count}', String(requiredColumns.length))}
                        </summary>
                        <div className="upload-columns-chips">
                            {requiredColumns.map((col) => (
                                <span key={col} className="upload-column-chip">{col}</span>
                            ))}
                        </div>
                    </details>
                )}
            </div>
        </div>
    );
}