import { useState } from 'react';
import './App.css';
import { ErrorBoundary } from './ErrorBoundary';
import { UploadGate } from './UploadGate';
import { Dashboard } from './Dashboard';

export default function App() {
  const [ready, setReady] = useState(false);
  const [forceUpload, setForceUpload] = useState(false);
  const [lang, setLang] = useState<'vi' | 'en'>('vi');

  return (
    <ErrorBoundary>
      {!ready ? (
        <UploadGate
          lang={lang}
          setLang={setLang}
          onReady={() => {
            setReady(true);
            setForceUpload(false);
          }}
          forceUpload={forceUpload}
        />
      ) : (
        <Dashboard
          lang={lang}
          setLang={setLang}
          onQuit={() => {
            setReady(false);
            setForceUpload(true);
          }}
        />
      )}
    </ErrorBoundary>
  );
}